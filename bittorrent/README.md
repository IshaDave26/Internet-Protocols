
# BitTorrent File Transfer Experiment

This project implements a distributed BitTorrent file transfer system to measure performance metrics across multiple peers. The implementation uses Python with the libtorrent library and Docker for containerization, allowing for consistent and reproducible experiments.

## Project Overview

This experiment measures BitTorrent protocol performance by transferring files of different sizes (10kB, 100kB, 1MB, 10MB) from an initial seeder to three leechers. The system records:
- Transfer time for each file size
- Throughput (calculated as file size × 3 / transfer time)
- Protocol overhead (total application layer data transferred / (file size × 3))

## Architecture

The system consists of:
1. **Tracker**: Coordinates peer discovery and communication
2. **Seeder**: The initial peer with the complete file
3. **Leechers (3)**: Peers that download the file and share pieces with each other

## Prerequisites

- Docker and Docker Compose
- Python 3.9+
- Sufficient disk space for experiment data

## Project Structure

```
bittorrent_experiment/
├── bt.py                  # Main BitTorrent implementation
├── docker-compose.yml     # Docker configuration for all peers
├── Dockerfile             # Container definition
├── run_experiments.sh     # Script to automate all experiments
├── aggregate_results.py   # Script to process and combine results
├── README.md              # This documentation
└── results/               # Directory for experiment results
```

## Setup Instructions

1. Make the experiment script executable:
   ```bash
   chmod +x run_experiments.sh
   ```

## Running the Experiments

### Full Experiment Suite

To run all experiments (370 total iterations across all file sizes):

```bash
./run_experiments.sh
```

This will:
1. Create necessary directories
2. Run experiments for each file size with the specified number of iterations:
   - A_10kB: 333 iterations
   - A_100kB: 33 iterations
   - A_1MB: 3 iterations
   - A_10MB: 1 iteration
3. Aggregate results into CSV files in the `results` directory

### Small Test Run

For testing purposes, you can run a smaller experiment:

```bash
./run_experiments.sh small
```

This runs only the 10kB file experiment with 5 iterations.

## How It Works

### Docker Containerization

The experiment uses Docker to create isolated environments for each peer:
- One container for the tracker
- One container for the seeder
- Three containers for the leechers

All containers share a common network, allowing them to communicate with each other.

### BitTorrent Implementation

The `bt.py` script implements:
1. **Torrent Creation**: The seeder creates a .torrent file with metadata
2. **Seeding**: The initial peer shares the complete file
3. **Leeching**: Other peers download pieces and share them with each other
4. **Metrics Collection**: The system records transfer times, throughput, and data overhead

### Data Collection and Analysis

For each experiment:
1. Individual metrics are saved for each leecher
2. Results are aggregated across all leechers
3. Summary statistics (mean, standard deviation) are calculated

## Results

After running the experiments, the following files are generated in the `results` directory:

- `all_leechers_results.csv`: Raw data from all experiments
- `leechers_performance_comparison.csv`: Performance comparison between leechers
- `all_leechers_summary.csv`: Summary statistics for each file size

These results can be imported into Excel for further analysis and visualization.

## Troubleshooting

### Common Issues

1. **Docker Errors**:
   ```bash
   # Check Docker service status
   systemctl status docker
   
   # Restart Docker if needed
   systemctl restart docker
   ```

2. **Permission Issues**:
   ```bash
   # Make sure you have permissions to write to the results directory
   chmod -R 777 results/
   ```

3. **Network Problems**:
   ```bash
   # Check if Docker network is created
   docker network ls
   
   # Recreate network if needed
   docker-compose down
   docker network prune
   ```

4. **Tracker Not Responding**:
   ```bash
   # Check tracker logs
   docker-compose logs tracker
   ```

## Technical Details

### BitTorrent Protocol Implementation

The implementation uses libtorrent's Python bindings to handle:
- Torrent file creation and parsing
- Peer discovery via the tracker
- Piece selection and transfer
- Connection management

### Performance Metrics

1. **Transfer Time**: Measured from when the leecher starts downloading until it has the complete file
2. **Throughput**: Calculated as `(file_size * 8 * 3) / (transfer_time * 1000)` in kbps
3. **Transfer Ratio**: Calculated as `total_data_transferred / (file_size * 3)`

## Conclusion

This experiment demonstrates the efficiency and overhead of the BitTorrent protocol for different file sizes. The results show how BitTorrent's peer-to-peer approach compares to traditional client-server models, particularly in terms of scalability and bandwidth utilization.

