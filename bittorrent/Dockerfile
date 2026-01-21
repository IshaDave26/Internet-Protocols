FROM python:3.9-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    libboost-all-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install libtorrent and other dependencies
RUN pip install libtorrent numpy pandas openpyxl

# Create app directory
WORKDIR /app

# Copy the script
COPY bt.py /app/

# Create data directory
RUN mkdir -p /data

CMD ["python", "/app/bt.py"] 