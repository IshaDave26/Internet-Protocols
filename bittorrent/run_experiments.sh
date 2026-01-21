#!/bin/bash

#make files for transfer
dd if=/dev/zero of=A_10kB bs=10k count=1
dd if=/dev/zero of=A_100kB bs=100k count=1
dd if=/dev/zero of=A_1MB bs=1M count=1
dd if=/dev/zero of=A_10MB bs=10M count=1

# Create directories for downloads and results
mkdir -p downloads_peer1 downloads_peer2 downloads_peer3 results

# Function to run a single experiment
run_experiment() {
    local file_path=$1
    local iterations=$2
    local result_dir=$3
    
    echo "Starting experiment: ${file_path} file (${iterations} iterations)"
    export FILE_PATH=${file_path}
    export ITERATIONS=${iterations}

    # Start tracker
    echo "Starting tracker..."
    docker-compose up -d tracker
    sleep 2  # Give tracker time to start

    # Start seeder
    echo "Starting seeder..."
    docker-compose up -d --build seeder

    # Wait for the seeder to create the torrent file
    echo "Waiting for torrent file to be created..."
    timeout=30
    while [ ! -f "${FILE_PATH}.torrent" ] && [ $timeout -gt 0 ]; do
        sleep 1
        timeout=$((timeout-1))
        echo -n "."
    done
    echo ""

    if [ ! -f "${FILE_PATH}.torrent" ]; then
        echo "Error: Torrent file was not created within the timeout period."
        docker-compose down
        exit 1
    fi

    # Start leechers
    echo "Torrent file created. Starting leechers..."
    docker-compose up --build leecher1 leecher2 leecher3
    docker-compose down

    # Create directory for this file size if it doesn't exist
    mkdir -p results/${result_dir}
    
    # Move result files to results directory, organizing by file size
    echo "Moving result files to results directory..."
    
    # Move leecher-specific files to the appropriate directory
    mv ${size_category}_*_results.csv results/${result_dir}/ 2>/dev/null || true
    
    # Clean up downloaded files but preserve result files
    rm -rf downloads_peer1/* downloads_peer2/* downloads_peer3/*
    
    echo "Experiment completed for ${file_path}!"
}

# Check if we should run in small experiment mode
if [ "$1" == "small" ]; then
    echo "Running small experiment with fewer iterations"
    run_experiment "A_10kB" 5 "10kB"
    echo "Small experiment completed! Results are available in the results directory."
    
    # Run the aggregation script
    python aggregate_results.py
    
    exit 0
fi

# Full experiment suite
echo "Running full experiment suite"

# Experiment 1: A_10kB file (333 iterations)
run_experiment "A_10kB" 333 "10kB"

# Experiment 2: A_100kB file (33 iterations)
run_experiment "A_100kB" 33 "100kB"

# Experiment 3: A_1MB file (3 iterations)
run_experiment "A_1MB" 3 "1MB"

# Experiment 4: A_10MB file (1 iteration)
run_experiment "A_10MB" 1 "10MB"

# Run the aggregation script
echo "Aggregating results..."
python aggregate_results.py

echo "All experiments completed! Results are available in the results directory"

# Clean up temporary files
rm -rf downloads_peer1 downloads_peer2 downloads_peer3 *.torrent