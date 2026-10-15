FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Seed initial database
RUN python database/seed_synthetic_edtech_data.py

# Expose Streamlit and FastAPI ports
EXPOSE 8501 8000

# Start Streamlit dashboard by default
CMD ["streamlit", "run", "app/dashboard_ui.py", "--server.port=8501", "--server.address=0.0.0.0"]
