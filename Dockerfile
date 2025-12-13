FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Expose port 80 (so we can access without port number)
EXPOSE 80

# Change to backend directory where app.py is
WORKDIR /app/backend

# Run Flask on port 80
CMD ["python", "app.py"]