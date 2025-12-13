FROM python:3.10-slim

WORKDIR /app

# Install Docker CLI (to run docker commands from inside container)
RUN apt-get update && \
    apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Expose port 8080
EXPOSE 8080

# Set working directory to backend
WORKDIR /app/backend

# Run the Flask app
CMD ["python", "app.py"]