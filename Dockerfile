# Includes Playwright + Chromium + all OS deps preinstalled
FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

# Prevent Python from buffering logs
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# (Optional, usually not needed with this base image)
# RUN python -m playwright install chromium

# Copy your code
COPY . .

# Streamlit settings (optional hardening)
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Expose Streamlit’s default port
EXPOSE 8501

# Launch the app
CMD ["streamlit", "run", "frontend/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]