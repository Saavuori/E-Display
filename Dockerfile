# Use standard Python 3.11 slim image
FROM python:3.11-slim-bookworm

# Set working directory
WORKDIR /app

# Ensure Python output is sent straight to terminal (e.g. your container log)
# without being first buffered and that you can see the output of your application (e.g. django logs) in real time.
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for Pillow and hardware access
RUN apt-get update && apt-get install -y \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage cache
COPY requirements.txt .

# Install Python dependencies
# Note: RPi.GPIO and spidev might need --break-system-packages or virtualenv in some distros, 
# but in docker slim containers pip install is usually fine as root.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for artifacts if it doesn't exist
RUN mkdir -p pic

# Expose port for API
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
