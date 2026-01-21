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

import socket


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
            
            # Use environment variable for tracker host if available
            tracker_host = os.environ.get('TRACKER_HOST', 'localhost')
            tracker_port = os.environ.get('TRACKER_PORT', '6969')
            t.add_tracker(f"http://{tracker_host}:{tracker_port}/announce")
            
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
        
        # Force initial announce
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
            
            # Force periodic announces
            if int(time.time()) % 30 == 0:
                h.force_reannounce()
                h.force_dht_announce()
            
            time.sleep(1)

    def run_leecher(self, torrent_path: str):
        try:
            for iteration in range(self.iterations):
                logger.info(f"\nStarting iteration {iteration + 1}/{self.iterations}")
                
                if not os.path.exists(torrent_path):
                    raise FileNotFoundError(f"Torrent file not found: {torrent_path}")
                
                logger.info(f"Found torrent file: {torrent_path}")
                
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
                
                # Set proper flags for leecher - allow both download and upload
                h.set_flags(lt.torrent_flags.auto_managed)
                h.unset_flags(lt.torrent_flags.upload_mode)
                
                # Force initial announce to tracker
                h.force_reannounce()
                h.force_dht_announce()
                
                # Set piece priorities
                for i in range(info.num_pieces()):
                    h.piece_priority(i, 7)  # Maximum priority
                
                my_port = session.listen_port()
                logger.info(f"Listening on port {my_port}")
                logger.info("Waiting for peers from tracker...")
                
                start_time = time.time()
                last_downloaded = 0
                last_uploaded = 0
                transfer_started = False
                download_complete = False
                unique_peers = set()
                peer_count = 0
                last_progress = 0
                
                while True:
                    s = h.status()
                    alerts = session.pop_alerts()
                    for a in alerts:
                        if isinstance(a, lt.peer_connect_alert):
                            ip = str(a.endpoint[0])
                            if ip not in unique_peers:
                                unique_peers.add(ip)
                                peer_count += 1
                                logger.info(f"Connected to peer: {ip}")
                        elif isinstance(a, lt.piece_finished_alert):
                            logger.info(f"Piece {a.piece_index} downloaded - available for sharing")
                        elif isinstance(a, lt.tracker_announce_alert):
                            logger.info(f"Tracker announce: {a.message()}")
                        elif isinstance(a, lt.tracker_reply_alert):
                            logger.info(f"Tracker reply: {a.message()}")
                    
                    current_downloaded = s.total_download
                    current_uploaded = s.total_upload
                    current_progress = s.progress * 100
                    
                    if current_progress > last_progress:
                        logger.info(f"Progress update: {current_progress:.2f}%")
                        last_progress = current_progress
                    
                    if current_downloaded > last_downloaded:
                        if not transfer_started:
                            transfer_started = True
                            logger.info("Data transfer started")
                        download_rate = (current_downloaded - last_downloaded) / 1024
                        logger.info(f"Downloading at {download_rate:.1f} kB/s")
                    last_downloaded = current_downloaded
                    
                    if current_uploaded > last_uploaded:
                        upload_rate = (current_uploaded - last_uploaded) / 1024
                        logger.info(f"Uploading at {upload_rate:.1f} kB/s")
                    last_uploaded = current_uploaded
                    
                    print(f"\rIteration {iteration + 1}/{self.iterations} - "
                          f"Progress: {s.progress*100:.2f}% "
                          f"Down: {s.download_rate/1024:.1f} kB/s "
                          f"Up: {s.upload_rate/1024:.1f} kB/s "
                          f"Total Peers: {peer_count} "
                          f"Total: {s.total_download/1024:.1f} kB "
                          f"Pieces: {s.num_pieces} "
                          f"State: {s.state}", end='')
                    
                    if s.is_finished:
                        if not download_complete:
                            print(f"\nDownload complete for iteration {iteration + 1}!")
                            downloaded_path = os.path.join(self.save_dir, os.path.basename(self.file_path))
                            logger.info(f"File downloaded successfully: {downloaded_path}")
                            
                            # Calculate metrics
                            transfer_time = time.time() - start_time
                            file_size = os.path.getsize(downloaded_path)
                            throughput = (file_size * 8 * 3) / (transfer_time * 1000)  # Convert to kbps
                            
                            # FIXED: Calculate total application layer data transferred
                            # We need to estimate the total data transferred among all four peers
                            # Since we only have data from this peer, we need to make an estimation
                            
                            # Data transferred by this peer
                            this_peer_data = s.total_upload + s.total_download
                            
                            # Estimate total data transferred by all peers
                            # In a typical BitTorrent setup with 1 seeder and 3 leechers:
                            # 1. Seeder uploads approximately file_size to each leecher (3 * file_size total)
                            # 2. Leechers share pieces with each other
                            # 3. Each leecher downloads approximately file_size and uploads some fraction
                            
                            # A reasonable estimation based on the problem statement:
                            # - Seeder uploads: ~3 * file_size (to 3 leechers)
                            # - Each leecher downloads: ~file_size
                            # - Each leecher uploads: varies, but we can estimate from our measurements
                            
                            # Estimate total data across all peers
                            seeder_upload = 3 * file_size  # Seeder uploads to 3 leechers
                            leecher_download = 3 * file_size  # 3 leechers each download the file
                            
                            # Estimate leecher uploads based on our measurements
                            # If this peer uploaded X, we assume other peers upload similarly
                            leecher_upload = 3 * s.total_upload  # Estimate for all 3 leechers
                            
                            # Total estimated data transferred
                            estimated_total_data = seeder_upload + leecher_download + leecher_upload
                            
                            # Calculate the ratio as requested: total data / (file_size * 3)
                            transfer_ratio = estimated_total_data / (file_size * 3)
                            
                            logger.info(f"This peer data transferred: {this_peer_data} bytes")
                            logger.info(f"Estimated total data transferred among all peers: {estimated_total_data} bytes")
                            logger.info(f"Transfer ratio (total data / (file_size * 3)): {transfer_ratio:.4f}")
                            
                            # Save individual result for this iteration
                            try:
                                save_individual_result(transfer_time, throughput, downloaded_path, 
                                                      iteration + 1, estimated_total_data, transfer_ratio)
                                logger.info("Individual result saved successfully")
                            except Exception as e:
                                logger.error(f"Failed to save individual result: {e}")
                            
                            self.transfer_times.append(transfer_time)
                            self.throughputs.append(throughput)
                            
                            # Also track transfer ratios for aggregation
                            if not hasattr(self, 'transfer_ratios'):
                                self.transfer_ratios = []
                            self.transfer_ratios.append(transfer_ratio)
                            
                            logger.info(f"Transfer time: {transfer_time:.2f} seconds")
                            logger.info(f"Throughput (for 3 peers): {throughput:.2f} kbps")
                            
                            h.pause()
                            session.remove_torrent(h)
                            download_complete = True
                            
                            if iteration < self.iterations - 1:
                                # Remove the file only if it's not the last iteration
                                os.remove(downloaded_path)
                                break  # Break inner loop to start next iteration
                            else:
                                # Calculate and save final results
                                avg_transfer_time = np.mean(self.transfer_times)
                                avg_throughput = np.mean(self.throughputs)
                                std_dev_throughput = np.std(self.throughputs)
                                avg_transfer_ratio = np.mean(self.transfer_ratios)
                                std_dev_transfer_ratio = np.std(self.transfer_ratios)
                                
                                logger.info(f"\nFinal Results after {self.iterations} iterations:")
                                logger.info(f"Average Transfer Time: {avg_transfer_time:.2f} seconds")
                                logger.info(f"Average Throughput: {avg_throughput:.2f} kbps")
                                logger.info(f"Throughput Std Dev: {std_dev_throughput:.2f} kbps")
                                logger.info(f"Average Transfer Ratio: {avg_transfer_ratio:.4f}")
                                logger.info(f"Transfer Ratio Std Dev: {std_dev_transfer_ratio:.4f}")
                                
                                # Save results with standard deviation
                                try:
                                    save_results(avg_transfer_time, avg_throughput, std_dev_throughput, 
                                                self.file_path, avg_transfer_ratio, std_dev_transfer_ratio)
                                    logger.info("Final results saved successfully")
                                except Exception as e:
                                    logger.error(f"Failed to save final results: {e}")
                                
                                break  # Break inner loop after saving results
                    
                    if time.time() - start_time > 30 and not transfer_started:
                        if s.total_download == 0:
                            print("\nTimeout reached - no data received")
                            break
                    
                    # Force periodic announces
                    if int(time.time()) % 30 == 0:
                        h.force_reannounce()
                        h.force_dht_announce()
                    
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error in leecher: {str(e)}")
            raise

def save_individual_result(transfer_time, throughput, file_name, iteration, total_data_transferred, transfer_ratio):
    """Save individual experiment result to ensure data persistence"""
    file_size = os.path.getsize(file_name)
    if file_size <= 10 * 1024:
        size_category = "10kB"
    elif file_size <= 100 * 1024:
        size_category = "100kB"
    elif file_size <= 1024 * 1024:
        size_category = "1MB"
    else:
        size_category = "10MB"
    
    # Get leecher ID from hostname or environment variable
    try:
        leecher_id = socket.gethostname()
        if 'leecher' not in leecher_id.lower():
            leecher_id = os.environ.get('LEECHER_ID', 'unknown_leecher')
    except:
        leecher_id = os.environ.get('LEECHER_ID', 'unknown_leecher')
    
    # Create pandas DataFrame for the result
    data = {
        'Leecher ID': [leecher_id],
        'Transfer Time': [transfer_time],
        'Throughput': [throughput],
        'File Size': [file_size],
        'Size Category': [size_category],
        'Iteration': [iteration],
        'Total Data Transferred': [total_data_transferred],
        'Transfer Ratio': [transfer_ratio],
        'Timestamp': [datetime.now().isoformat()]
    }
    result_df = pd.DataFrame(data)
    
    # First priority: /results directory (mounted to host)
    if os.path.exists('/results'):
        try:
            # Ensure directory is writable
            if os.access('/results', os.W_OK):
                # Create a separate file for each leecher
                leecher_file = os.path.join('/results', f"{size_category}_{leecher_id}_results.csv")
                if os.path.exists(leecher_file):
                    leecher_df = pd.read_csv(leecher_file)
                    leecher_df = pd.concat([leecher_df, result_df], ignore_index=True)
                else:
                    leecher_df = result_df.copy()
                
                leecher_df.to_csv(leecher_file, index=False)
                
                logger.info(f"Individual result saved to leecher-specific file: {leecher_file}")
                return
            else:
                logger.error("/results directory exists but is not writable")
        except Exception as e:
            logger.error(f"Error saving to /results: {e}")
    
    # Second priority: /data directory (also mounted to host)
    if os.path.exists('/data'):
        try:
            # Ensure directory is writable
            if os.access('/data', os.W_OK):
                # Create a separate file for each leecher
                leecher_file = os.path.join('/data', f"{size_category}_{leecher_id}_results.csv")
                if os.path.exists(leecher_file):
                    leecher_df = pd.read_csv(leecher_file)
                    leecher_df = pd.concat([leecher_df, result_df], ignore_index=True)
                else:
                    leecher_df = result_df.copy()
                
                leecher_df.to_csv(leecher_file, index=False)
                
                logger.info(f"Individual result saved to leecher-specific file: {leecher_file}")
                return
            else:
                logger.error("/data directory exists but is not writable")
        except Exception as e:
            logger.error(f"Error saving to /data: {e}")
    
    # Last resort: current directory (likely not mounted to host)
    logger.warning("Could not save to mounted volumes, saving to current directory (may not be visible on host)")
    try:
        leecher_file = os.path.join(os.getcwd(), f"{size_category}_{leecher_id}_results.csv")
        if os.path.exists(leecher_file):
            leecher_df = pd.read_csv(leecher_file)
            leecher_df = pd.concat([leecher_df, result_df], ignore_index=True)
        else:
            leecher_df = result_df.copy()
        
        leecher_df.to_csv(leecher_file, index=False)
        
        logger.info(f"Individual result saved to leecher-specific file (WARNING: This may not be visible on host)")
    except Exception as e:
        logger.error(f"Failed to save results anywhere: {e}")

def save_results(transfer_time, throughput, std_dev, file_name, avg_transfer_ratio, std_dev_transfer_ratio):
    """Save aggregated results from multiple iterations"""
    file_size = os.path.getsize(file_name)
    if file_size <= 10 * 1024:
        size_category = "10kB"
    elif file_size <= 100 * 1024:
        size_category = "100kB"
    elif file_size <= 1024 * 1024:
        size_category = "1MB"
    else:
        size_category = "10MB"

    # Get leecher ID from hostname or environment variable
    try:
        # Try to get hostname first (will be container name in Docker)
        leecher_id = socket.gethostname()
        # If hostname doesn't contain 'leecher', try environment variable
        if 'leecher' not in leecher_id.lower():
            leecher_id = os.environ.get('LEECHER_ID', 'unknown_leecher')
    except:
        leecher_id = os.environ.get('LEECHER_ID', 'unknown_leecher')

    # Create pandas DataFrame for the aggregated result
    data = {
        'Leecher ID': [leecher_id],
        'File Size': [file_size],
        'Size Category': [f"{size_category} file"],
        'Avg Transfer Time': [transfer_time],
        'Avg Throughput': [throughput],
        'Std Dev Throughput': [std_dev],
        'Avg Transfer Ratio': [avg_transfer_ratio],
        'Std Dev Transfer Ratio': [std_dev_transfer_ratio],
        'Timestamp': [datetime.now().isoformat()]
    }
    result_df = pd.DataFrame(data)

    # First priority: /results directory (mounted to host)
    if os.path.exists('/results'):
        try:
            # Ensure directory is writable
            if os.access('/results', os.W_OK):
                # Only update the master results file with all leechers
                master_csv = os.path.join('/results', "bt_all_leechers_aggregated.csv")
                if os.path.exists(master_csv):
                    master_df = pd.read_csv(master_csv)
                    master_df = pd.concat([master_df, result_df], ignore_index=True)
                else:
                    master_df = result_df.copy()
                
                master_df.to_csv(master_csv, index=False)
                
                logger.info(f"Aggregated results added to master file: {master_csv}")
                return
            else:
                logger.error("/results directory exists but is not writable")
        except Exception as e:
            logger.error(f"Error saving to /results: {e}")
    
    # Second priority: /data directory (also mounted to host)
    if os.path.exists('/data'):
        try:
            # Ensure directory is writable
            if os.access('/data', os.W_OK):
                # Only update the master results file with all leechers
                master_csv = os.path.join('/data', "bt_all_leechers_aggregated.csv")
                if os.path.exists(master_csv):
                    master_df = pd.read_csv(master_csv)
                    master_df = pd.concat([master_df, result_df], ignore_index=True)
                else:
                    master_df = result_df.copy()
                
                master_df.to_csv(master_csv, index=False)
                
                logger.info(f"Aggregated results added to master file: {master_csv}")
                return
            else:
                logger.error("/data directory exists but is not writable")
        except Exception as e:
            logger.error(f"Error saving to /data: {e}")
    
    # Last resort: current directory (likely not mounted to host)
    logger.warning("Could not save to mounted volumes, saving to current directory (may not be visible on host)")
    try:
        master_csv = os.path.join(os.getcwd(), "bt_all_leechers_aggregated.csv")
        if os.path.exists(master_csv):
            master_df = pd.read_csv(master_csv)
            master_df = pd.concat([master_df, result_df], ignore_index=True)
        else:
            master_df = result_df.copy()
        
        master_df.to_csv(master_csv, index=False)
        
        logger.info(f"Aggregated results added to master file: {master_csv} (WARNING: This may not be visible on host)")
    except Exception as e:
        logger.error(f"Failed to save results anywhere: {e}")

# Add this function to check and create directories at startup
def check_directories():
    """Check if mounted directories exist and are writable"""
    logger.info("=== CHECKING MOUNTED DIRECTORIES ===")
    
    for directory in ['/results', '/data']:
        if os.path.exists(directory):
            logger.info(f"{directory} exists")
            if os.access(directory, os.W_OK):
                logger.info(f"{directory} is writable")
                # Try to create a test file
                test_file = os.path.join(directory, '.write_test')
                try:
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    logger.info(f"Successfully verified write access to {directory}")
                except Exception as e:
                    logger.error(f"Cannot write to {directory} despite permissions check: {e}")
            else:
                logger.error(f"{directory} exists but is not writable")
        else:
            logger.error(f"{directory} does not exist")
    
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"Current working directory is writable: {os.access(os.getcwd(), os.W_OK)}")

# Add a new function to analyze results from all leechers
def analyze_all_leechers_results():
    """Analyze and compare results from all leechers"""
    results_file = os.path.join('/results', "all_leechers_results.csv")
    
    if not os.path.exists(results_file):
        logger.error(f"Cannot analyze leecher results: {results_file} not found")
        return
    
    try:
        # Load the combined results
        df = pd.read_csv(results_file)
        
        # Add a new analysis that combines data from all leechers for each experiment
        # Group by Size Category and calculate the total data transferred
        total_data_analysis = df.groupby(['Size Category']).agg({
            'File Size': 'first',  # Just take the first file size for each category
            'Total Data Transferred': 'sum',  # Sum up all data transferred
            'Transfer Ratio': 'mean'  # Average of the transfer ratios
        }).reset_index()
        
        # Calculate a more accurate transfer ratio based on combined data
        total_data_analysis['Combined Transfer Ratio'] = total_data_analysis['Total Data Transferred'] / (total_data_analysis['File Size'] * 3)
        
        # Save this analysis
        combined_analysis_file = os.path.join('/results', "combined_data_analysis.csv")
        total_data_analysis.to_csv(combined_analysis_file, index=False)
        
        logger.info(f"Combined data analysis saved to {combined_analysis_file}")
        
        # Group by leecher ID and size category
        grouped = df.groupby(['Leecher ID', 'Size Category'])
        
        # Calculate statistics for each group - now including Transfer Ratio
        stats = grouped.agg({
            'Transfer Time': ['mean', 'std', 'min', 'max'],
            'Throughput': ['mean', 'std', 'min', 'max'],
            'Transfer Ratio': ['mean', 'std', 'min', 'max']
        }).reset_index()
        
        # Save the analysis
        analysis_file = os.path.join('/results', "leechers_performance_comparison.csv")
        stats.to_csv(analysis_file, index=False)
        
        logger.info(f"Leecher performance comparison saved to {analysis_file}")
        
        # Create a summary with averages across all leechers - now including Transfer Ratio
        summary = df.groupby('Size Category').agg({
            'Transfer Time': ['mean', 'std'],
            'Throughput': ['mean', 'std'],
            'Transfer Ratio': ['mean', 'std']
        }).reset_index()
        
        summary_file = os.path.join('/results', "all_leechers_summary.csv")
        summary.to_csv(summary_file, index=False)
        
        logger.info(f"Summary across all leechers saved to {summary_file}")
        
    except Exception as e:
        logger.error(f"Error analyzing leecher results: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python bt.py <mode> <file_path> <save_dir> <iterations>")
        print("Example seeder: python bt.py seeder A_10kB . 5")
        print("Example leecher: python bt.py leecher A_10kB downloads 5")
        sys.exit(1)

    mode = sys.argv[1]
    file_path = sys.argv[2]
    save_dir = sys.argv[3]
    iterations = int(sys.argv[4])

    if mode not in ['seeder', 'leecher']:
        print("Mode must be either 'seeder' or 'leecher'")
        sys.exit(1)

    # Check directories at startup
    check_directories()
    
    # Create save_dir if it doesn't exist
    os.makedirs(save_dir, exist_ok=True)

    experiment = TorrentExperiment(file_path, save_dir, mode, iterations)
    torrent_path = f"{file_path}.torrent"

    try:
        if mode == 'seeder':
            # Simple check if tracker is running by trying to connect to it
            tracker_host = os.environ.get('TRACKER_HOST', 'localhost')
            tracker_port = int(os.environ.get('TRACKER_PORT', '6969'))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect((tracker_host, tracker_port))
                logger.info(f"Tracker running at {tracker_host}:{tracker_port}")
            except ConnectionRefusedError:
                logger.error(f"Cannot connect to tracker at {tracker_host}:{tracker_port}")
                raise Exception(f"Tracker not available at {tracker_host}:{tracker_port}")
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
