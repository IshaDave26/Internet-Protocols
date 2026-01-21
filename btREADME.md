# BitTorrent File Transfer Experiment

This project implements a BitTorrent file transfer system using Python and libtorrent. It supports both seeding and leeching operations with multiple iterations for experimental measurements.

## Prerequisites

### System Requirements
- Linux/Unix system (tested on Kali Linux)
- Python 3.x
- pip (Python package manager)

### Required Packages
Install the following packages:
```bash
# Install Python dependencies
pip install libtorrent numpy pandas

# Install opentracker (BitTorrent tracker)
apt-get update
apt-get install opentracker
```

## Setup

1. Create a directory for your experiment:
```bash
mkdir bittorrent_test
cd bittorrent_test
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate
```

3. Save the Python script as `btorr.py` in your directory.

4. Create test files of different sizes (you only need to create each file once):
```bash
# Create one file of each size for testing
dd if=/dev/urandom of=A_10kB bs=1024 count=10
```

The same file can be used for multiple iterations because:
1. The seeder keeps the original file and shares it
2. The leecher downloads it multiple times (specified by the iterations parameter)
3. Each iteration:
   - Downloads the file
   - Calculates metrics
   - Deletes the downloaded copy
   - Starts a new download
4. The final metrics are averaged across all iterations

## Running the Experiment

### 1. Start the Tracker
First, start the BitTorrent tracker manually on each vm terminal:
```bash
opentracker -p 8000
```

### 2. Start the Seeder
On the first machine (VM1), on a separate terminal than the tracker run:
```bash
python btorr.py seeder A_10kB . 5
```
This will:
- Create a torrent file (A_10kB.torrent)
- Start seeding the file
- Run for 5 iterations

### 3. Copy the Torrent File
Copy the torrent file from seeder to leecher. Replace the IP addresses with your actual VM IPs(this needs to be done for all VMs):
```bash
# On leecher
scp root@<seeder_IP>:/root/bittorrent_test/A_10kB.torrent .
```

### 4. Start the Leecher
On the second machine (VM2), run:
```bash
# Create downloads directory
mkdir downloads

# Run leecher
python btorr.py leecher A_10kB downloads 5
```

The process flow is now:
1. Start tracker manually
2. Start seeder on VM1
3. Copy torrent file from VM1 to VM2
4. Start leecher on VM2

## Command Line Arguments
The script takes four arguments:
1. `mode`: Either 'seeder' or 'leecher'
2. `file_path`: Path to the file to share/download
3. `save_dir`: Directory to save downloaded files
4. `iterations`: Number of times to repeat the transfer

Example:
```bash
python btorr.py <mode> <file_path> <save_dir> <iterations>
```

## Results
- Results are automatically saved to `transfer_results.xlsx`
- The Excel file contains:
  - Average throughput
  - Standard deviation
  - Overhead measurements
  - Separate columns for different file sizes (10kB, 100kB, 1MB, 10MB)

## Network Setup
For best results:
1. Use VirtualBox with NAT Network
2. Configure both VMs to use the same NAT Network
3. Ensure VMs can ping each other
4. Make sure port 6881 is not blocked

## Troubleshooting

### Common Issues:
1. **Tracker not starting**:
   ```bash
   # Check if tracker is running
   netstat -tuln | grep 8000
   # Start tracker manually if needed
   opentracker -p 8000
   ```

2. **Connection issues**:
   ```bash
   # Check network connectivity
   ping <other_vm_ip>
   # Check if port is open
   nc -zv <other_vm_ip> 6881
   ```

3. **Permission issues**:
   ```bash
   # Run with sudo if needed
   sudo python btorr.py seeder A_10kB . 5
   ```

### File Cleanup
To clean up between experiments:
```bash
# Remove torrent files
rm *.torrent

# Remove downloaded files
rm -rf downloads/*

# Remove results file
rm transfer_results.xlsx
```

## Notes
- The seeder will continue running until manually stopped (Ctrl+C)
- The leecher will run for the specified number of iterations
- Each iteration's metrics are calculated and averaged at the end
- Results are automatically saved after each leecher completion
- The system supports simultaneous upload while downloading
- Peers continue seeding after download completion

## File Structure
    bittorrent_test/
├── btorr.py
├── A_10kB
├── A_100kB
├── A_1MB
├── A_10MB
├── .torrent
├── downloads/
└── transfer_results.xlsx