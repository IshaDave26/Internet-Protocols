import libtorrent as lt
import time
import sys
import os
import numpy as np
from datetime import datetime
import pandas as pd
from pathlib import Path
import logging
from typing import Dict
import tempfile
import socket
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TorrentExperiment:
    def __init__(self, file_path: str, save_dir: str, mode: str, iterations: int):
        self.file_path = file_path
        self.save_dir = save_dir
        self.mode = mode  # 'seeder' or 'leecher'
        self.iterations = iterations
        self.transfer_times = []
        self.throughputs = []
        
    def create_torrent(self) -> str:
        try:
            fs = lt.file_storage()
            lt.add_files(fs, self.file_path)
            t = lt.create_torrent(fs, 16384)
            t.set_creator('libtorrent python bindings')
            
            # Add both localhost and IP tracker
            t.add_tracker("http://localhost:8000/announce")
            
            abs_path = os.path.abspath(self.file_path)
            lt.set_piece_hashes(t, os.path.dirname(abs_path))
            
            torrent_data = t.generate()
            torrent_path = f"{self.file_path}.torrent"
            with open(torrent_path, 'wb') as f:
                f.write(lt.bencode(torrent_data))
            
            logger.info(f"Created torrent file: {torrent_path}")
            return torrent_path
        except Exception as e:
            logger.error(f"Error creating torrent file: {e}")
            raise

    def run_seeder(self, torrent_path: str):
        session = lt.session()
        settings = {
            'listen_interfaces': '0.0.0.0:6881',
            'enable_dht': True,
            'enable_lsd': True,
            'enable_upnp': True,
            'enable_natpmp': True,
            'alert_mask': lt.alert.category_t.all_categories,
            'active_limit': -1,
            'allow_multiple_connections_per_ip': True,
            'announce_to_all_trackers': True,
            'announce_to_all_tiers': True,
            'connection_speed': 500,
            'min_announce_interval': 30,
            'tracker_backoff': 20
        }
        session.apply_settings(settings)
        
        with open(torrent_path, 'rb') as f:
            torrent_data = f.read()
        info = lt.torrent_info(lt.bdecode(torrent_data))
        
        h = session.add_torrent({
            'ti': info,
            'save_path': str(Path(self.file_path).parent),
            'flags': lt.torrent_flags.seed_mode
        })
        
        h.force_reannounce()
        h.force_dht_announce()
        
        logger.info(f"Starting seeder for {self.file_path} on port 6881")
        logger.info(f"Waiting for connections...")
        
        last_uploaded = 0
        unique_peers = set()
        peer_count = 0
        
        while True:
            s = h.status()
            alerts = session.pop_alerts()
            for a in alerts:
                if isinstance(a, lt.peer_connect_alert):
                    ip = str(a.endpoint[0])
                    if ip not in unique_peers:
                        unique_peers.add(ip)
                        peer_count += 1
                        logger.info(f"New peer connected from {ip}")
                elif isinstance(a, lt.tracker_announce_alert):
                    logger.info(f"Tracker announce: {a.message()}")
                elif isinstance(a, lt.tracker_reply_alert):
                    logger.info(f"Tracker reply: {a.message()}")
                    
            current_uploaded = s.total_upload
            if current_uploaded > last_uploaded:
                upload_rate = (current_uploaded - last_uploaded) / 1024
                logger.info(f"Uploading data: {upload_rate:.1f} kB/s")
            last_uploaded = current_uploaded
            
            print(f"\rSeeding... "
                  f"Up: {s.upload_rate/1024:.1f} kB/s "
                  f"Total Peers: {peer_count} "
                  f"Total Uploaded: {s.total_upload/1024:.1f} kB "
                  f"State: {s.state} "
                  f"Pieces: {s.num_pieces}", end='')
            
            if int(time.time()) % 30 == 0:
                h.force_reannounce()
                h.force_dht_announce()
            
            time.sleep(1)

    def run_leecher(self, torrent_path: str):
        try:
            for iteration in range(self.iterations):
                logger.info(f"\nStarting iteration {iteration + 1}/{self.iterations}")
                
                session = lt.session()
                settings = {
                    'listen_interfaces': '0.0.0.0:0',
                    'enable_dht': True,
                    'enable_lsd': True,
                    'enable_upnp': True,
                    'enable_natpmp': True,
                    'alert_mask': lt.alert.category_t.all_categories,
                    'active_limit': -1,
                    'allow_multiple_connections_per_ip': True,
                    'announce_to_all_trackers': True,
                    'announce_to_all_tiers': True,
                    'connection_speed': 500,
                    'min_announce_interval': 30,
                    'tracker_backoff': 20,
                    'piece_timeout': 20,
                    'request_timeout': 20,
                    'peer_connect_timeout': 20,
                    'upload_rate_limit': 0,
                    'download_rate_limit': 0
                }
                session.apply_settings(settings)
                
                with open(torrent_path, 'rb') as f:
                    torrent_data = f.read()
                info = lt.torrent_info(lt.bdecode(torrent_data))
                
                h = session.add_torrent({
                    'ti': info,
                    'save_path': self.save_dir
                })
                
                h.set_flags(lt.torrent_flags.auto_managed)
                h.unset_flags(lt.torrent_flags.upload_mode)
                
                start_time = time.time()
                last_progress = -1
                peer_count = 0
                
                while True:
                    s = h.status()
                    alerts = session.pop_alerts()
                    for a in alerts:
                        if isinstance(a, lt.peer_connect_alert):
                            peer_count += 1
                    
                    current_progress = int(s.progress * 100)
                    if current_progress != last_progress:
                        print(f"\rProgress: {current_progress}% | "
                              f"Down: {s.download_rate/1024:.1f} kB/s | "
                              f"Up: {s.upload_rate/1024:.1f} kB/s | "
                              f"Peers: {peer_count}", end='', flush=True)
                        last_progress = current_progress
                    
                    if s.is_finished:
                        print("\nDownload complete!")
                        downloaded_path = os.path.join(self.save_dir, os.path.basename(self.file_path))
                        
                        transfer_time = time.time() - start_time
                        file_size = os.path.getsize(downloaded_path)
                        throughput = (file_size * 8 * 3) / (transfer_time * 1000)  # For 3 peers
                        
                        self.transfer_times.append(transfer_time)
                        self.throughputs.append(throughput)
                        
                        print(f"Transfer time: {transfer_time:.2f}s, Throughput: {throughput:.2f} kbps")
                        
                        h.pause()
                        session.remove_torrent(h)
                        
                        if iteration < self.iterations - 1:
                            os.remove(downloaded_path)
                        break
                    
                    time.sleep(0.1)
                    
        except Exception as e:
            logger.error(f"Error in leecher: {str(e)}")
            raise

def save_results(transfer_time, throughput, std_dev, file_name):
    EXCEL_FILE = "transfer_results.xlsx"
    
    file_size = os.path.getsize(file_name)
    if file_size <= 10 * 1024:
        size_category = "10kB file"
    elif file_size <= 100 * 1024:
        size_category = "100kB file"
    elif file_size <= 1024 * 1024:
        size_category = "1MB file"
    else:
        size_category = "10MB file"

    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE, index_col=0)
    else:
        columns = [
            '10kB file_Average', '10kB file_Std. Dev.',
            '100kB file_Average', '100kB file_Std. Dev.',
            '1MB file_Average', '1MB file_Std. Dev.',
            '10MB file_Average', '10MB file_Std. Dev.',
            '10kB file_Overhead', '100kB file_Overhead',
            '1MB file_Overhead', '10MB file_Overhead'
        ]
        df = pd.DataFrame(columns=columns, index=['BitTorrent'])

    df.at['BitTorrent', f'{size_category}_Average'] = throughput
    df.at['BitTorrent', f'{size_category}_Std. Dev.'] = std_dev
    df.at['BitTorrent', f'{size_category}_Overhead'] = 3.0

    df.to_excel(EXCEL_FILE)
    logger.info(f"Results saved to {EXCEL_FILE}")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python btorr.py <mode> <file_path> <save_dir> <iterations>")
        print("Example seeder: python btorr.py seeder A_10kB . 5")
        print("Example leecher: python btorr.py leecher A_10kB downloads 5")
        sys.exit(1)

    mode = sys.argv[1]
    file_path = sys.argv[2]
    save_dir = sys.argv[3]
    iterations = int(sys.argv[4])

    if mode not in ['seeder', 'leecher']:
        print("Mode must be either 'seeder' or 'leecher'")
        sys.exit(1)

    os.makedirs(save_dir, exist_ok=True)

    experiment = TorrentExperiment(file_path, save_dir, mode, iterations)
    torrent_path = f"{file_path}.torrent"

    try:
        if mode == 'seeder':
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(('localhost', 8000))
                logger.info("Tracker already running")
            except ConnectionRefusedError:
                print("Starting opentracker...")
                subprocess.Popen(['opentracker', '-p', '8000'])
                time.sleep(2)
                logger.info("Tracker started")
            finally:
                sock.close()
            
            torrent_path = experiment.create_torrent()
            experiment.run_seeder(torrent_path)
        else:
            experiment.run_leecher(torrent_path)
    except KeyboardInterrupt:
        print("\nExperiment stopped by user")
    except Exception as e:
        print(f"\nError: {str(e)}")