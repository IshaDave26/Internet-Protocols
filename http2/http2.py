import sys
import os
import time
import httpx
import uvicorn
import numpy as np
from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI()
FILE_DIRECTORY = os.getcwd()

def run_server(host, port):
    @app.get("/download/{filename}")
    async def download_file(filename: str):
        file_path = os.path.join(FILE_DIRECTORY, filename)
        if os.path.exists(file_path):
            return FileResponse(file_path, media_type="application/octet-stream", filename=filename)
        return {"error": "File not found"}
    
    print(f"Starting server at {host}:{port}")
    uvicorn.run(app, host=host, port=port, ssl_keyfile="key.pem", ssl_certfile="cert.pem", http="h11")

def run_client(server_ip, port, file_name, iterations):
    server_url = f"https://{server_ip}:{port}/download/{file_name}"
    transfer_times = []
    total_data_transferred = 0
    total_file_size_transferred = 0
    success_count = 0
    failure_count = 0
    cert_path = os.path.join(FILE_DIRECTORY, "cert.pem")
    
    with httpx.Client(http2=True, verify=cert_path) as client:
        for _ in range(iterations):
            start_time = time.time()
            response = client.get(server_url)
            end_time = time.time()
            
            if response.status_code == 200:
                file_size_bytes = len(response.content)
                file_size_kbits = (file_size_bytes * 8) / 1000
                elapsed_time = end_time - start_time
                total_data_transferred += len(response.content) + len(str(response.headers).encode())
                total_file_size_transferred += file_size_bytes
                transfer_times.append(elapsed_time)
                success_count += 1
            else:
                failure_count += 1

    if transfer_times:
        avg_throughput = file_size_kbits / np.mean(transfer_times)
        std_dev_throughput = np.std([file_size_kbits / t for t in transfer_times])
        overhead = total_data_transferred / total_file_size_transferred
    else:
        avg_throughput, std_dev_throughput, overhead = 0, 0, 0

    print(f"\nSummary for {file_name}:")
    print(f"Total Successful Transfers: {success_count}")
    print(f"Total Failed Transfers: {failure_count}")
    print(f"Average Throughput: {avg_throughput:.2f} kbps")
    print(f"Standard Deviation: {std_dev_throughput:.2f} kbps")
    print(f"Application Layer Overhead: {overhead:.2f}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py [server|client] [host] [port] [file_name] [iterations]")
        sys.exit(1)
    #python3 http2.py server 127.0.0.1 8080
    #python3 http2.py client 127.0.0.1 8080 A_10kB 2
    mode = sys.argv[1]
    if mode == "server":
        if len(sys.argv) < 4:
            print("Usage: python script.py server [host] [port]")
            sys.exit(1)
        host = sys.argv[2]
        port = int(sys.argv[3])
        run_server(host, port)
    elif mode == "client":
        if len(sys.argv) < 6:
            print("Usage: python script.py client [host] [port] [file_name] [iterations]")
            sys.exit(1)
        server_ip = sys.argv[2]
        port = int(sys.argv[3])
        file_name = sys.argv[4]
        iterations = int(sys.argv[5])
        run_client(server_ip, port, file_name, iterations)
    else:
        print("Invalid argument. Use 'server' or 'client'.")
