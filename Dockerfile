# Multi-stage build for DigitalOcean DNS Manager
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py .
COPY static/ ./static/
COPY VERSION .

# Version: use build arg if provided (CI), otherwise fall back to VERSION file
ARG APP_VERSION=""
RUN VERSION="${APP_VERSION:-$(cat VERSION | tr -d '[:space:]')}"; \
    sed -i "s/__VERSION__/${VERSION}/g" static/index.html

# Create .env file placeholder (will be populated at runtime)
RUN touch .env

# Expose port
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000/api/health')" || exit 1

# Run the application
CMD ["python", "app.py"]
