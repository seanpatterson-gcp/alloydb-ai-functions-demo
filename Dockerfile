# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY data_loader/ data_loader/
COPY SPEC.md README.md ./

# Cloud Run defaults to PORT 8080
ENV PORT=8080
EXPOSE 8080

# Run FastAPI via Uvicorn
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
