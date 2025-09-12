# Includes Playwright + Chromium + all OS deps preinstalled
# FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# # Prevent Python from buffering logs
# ENV PYTHONUNBUFFERED=1
# WORKDIR /app

# # Install Python deps
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# # (Optional, usually not needed with this base image)
# # RUN python -m playwright install chromium

# # Copy your code
# COPY . .

# # Streamlit settings (optional hardening)
# ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# # Expose Streamlit’s default port
# EXPOSE 8501

# # Launch the app
# CMD ["streamlit", "run", "frontend/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]


# A more minimal base image without Playwright, if you want to install it yourself
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (better layer cache)
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Cloud Run provides $PORT (defaults to 8080). Expose is optional.
EXPOSE 8080

# Run the app
# CMD ["streamlit", "run", "frontend/app.py", "--server.port", "8080", "--server.address", "0.0.0.0"]
CMD ["bash", "-c", "streamlit run frontend/app.py --server.address=0.0.0.0 --server.port=${PORT:-8080}"]