import http.server
import socketserver
import threading
import http.client
import os
import time
import sys
import numpy as np
import socket
import pandas as pd

def get_ip():
    # Get all network interfaces
    for interface in socket.if_nameindex():
        try:
            # Get the IP address for each interface
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Use a dummy connection to get the IP
                s.connect(('8.8.8.8', 80))
                ip = s.getsockname()[0]
                if not ip.startswith('127.') and not ip.startswith('172.'):
                    return ip
        except:
            continue
    return '127.0.0.1'

# Server code
def run_server(port=8080, directory="."):
    server_ip = get_ip()
    print(f"\nServer Information:")
    print(f"IP Address: {server_ip}")
    print(f"Port: {port}")
    print(f"Full Address: http://{server_ip}:{port}")

    class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

    handler_object = MyHttpRequestHandler
    
    # Bind to all available interfaces
    with socketserver.TCPServer(("0.0.0.0", port), handler_object) as httpd:
        print("\nServer is ready to accept connections...")
        httpd.serve_forever()

# Calculation function
def calculate_metrics(results, file_size, file_path):
    throughputs = [result[1] for result in results]
    avg_throughput = np.mean(throughputs)
    std_dev_throughput = np.std(throughputs)

    # Calculate overhead (total data transferred / file size)
    header_size = 500 * 8  # Convert to bits
    total_data_transferred = file_size + header_size
    overhead = total_data_transferred / file_size

    print(f"\nResults for {file_path}:")
    print(f"Throughput - Average: {avg_throughput:.2f} kbps")
    print(f"Throughput - Std Dev: {std_dev_throughput:.2f} kbps")
    print(f"Overhead Ratio: {overhead:.2f}\n")

    # Save to Excel
    EXCEL_FILE = "transfer_results.xlsx"
    
    # Determine file size category
    file_size_bytes = file_size / 8  # Convert bits to bytes
    if file_size_bytes <= 10 * 1024:
        size_category = "10kB file"
    elif file_size_bytes <= 100 * 1024:
        size_category = "100kB file"
    elif file_size_bytes <= 1024 * 1024:
        size_category = "1MB file"
    else:
        size_category = "10MB file"

    # Create or load existing DataFrame
    if os.path.exists(EXCEL_FILE):
        df = pd.read_excel(EXCEL_FILE, index_col=0)
    else:
        # Create DataFrame with the structure matching the table
        columns = [
            '10kB file_Average', '10kB file_Std. Dev.',
            '100kB file_Average', '100kB file_Std. Dev.',
            '1MB file_Average', '1MB file_Std. Dev.',
            '10MB file_Average', '10MB file_Std. Dev.',
            '10kB file_Overhead', '100kB file_Overhead',
            '1MB file_Overhead', '10MB file_Overhead'
        ]
        df = pd.DataFrame(columns=columns, index=['HTTP 1.1'])

    # Update the appropriate columns
    df.at['HTTP 1.1', f'{size_category}_Average'] = avg_throughput
    df.at['HTTP 1.1', f'{size_category}_Std. Dev.'] = std_dev_throughput
    df.at['HTTP 1.1', f'{size_category}_Overhead'] = overhead

    # Save DataFrame
    df.to_excel(EXCEL_FILE)
    print(f"Results saved to {EXCEL_FILE}")

# Client code
def run_client(host='localhost', port=8080, file_path='index.html', iterations=1):
    results = []

    for i in range(iterations):
        start_time = time.time()
        
        conn = http.client.HTTPConnection(host, port)
        conn.request("GET", f"/{file_path}")
        response = conn.getresponse()

        if response.status == 200:
            # Read the response content and get its size
            content = response.read()
            file_size = len(content) * 8  # Convert bytes to bits
            
            # Save the downloaded file
            with open(f"downloaded_{file_path}", 'wb') as f:
                f.write(content)
            
            end_time = time.time()
            transfer_time = end_time - start_time
            throughput = (file_size / transfer_time) / 1000  # Convert to kilobits per second
            results.append((transfer_time, throughput))
            
            # Calculate and print progress
            progress = ((i + 1) / iterations) * 100
            print(f"Progress: {progress:.2f}%", end='\r')

            # Only calculate metrics after the first iteration to get the correct file size
            if i == 0:
                first_file_size = file_size
        else:
            print(f"Failed to download file. Status: {response.status}, Reason: {response.reason}")

        conn.close()
        time.sleep(0.1)  # Small delay to avoid overwhelming the server

    print("\nDownload complete.")
    if results:  # Only calculate metrics if we have successful transfers
        calculate_metrics(results, first_file_size, file_path)
    return results

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py [server|client] [host] [port] [file_path] [iterations]")
        sys.exit(1)

    if sys.argv[1] == "server":
        run_server()
    elif sys.argv[1] == "client":
        if len(sys.argv) < 5:
            print("Usage: python script.py client [host] [port] [file_path] [iterations]")
            sys.exit(1)
        
        host = sys.argv[2]          # Get IP address from command line
        port = int(sys.argv[3])     # Get port from command line
        file_path = sys.argv[4]     # Get file path
        iterations = int(sys.argv[5]) if len(sys.argv) > 5 else 1  # Get iterations if provided
        
        results = run_client(host=host, port=port, file_path=file_path, iterations=iterations)
    else:
        print("Invalid argument. Use 'server' or 'client'.")
