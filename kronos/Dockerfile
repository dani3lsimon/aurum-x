FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# CPU-only torch first (large, cache-friendly layer)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Clone Kronos repo so model/ directory is in the Python path
RUN git clone https://github.com/shiyu-coder/Kronos /app

# Install remaining deps
RUN pip install --no-cache-dir fastapi uvicorn python-dotenv pandas httpx

# Override server with our version
COPY kronos_server.py /app/kronos_server.py

# Verify imports before container is considered healthy
RUN python -c "from model import Kronos, KronosTokenizer, KronosPredictor; print('Kronos imports OK')"

EXPOSE 8090

CMD ["uvicorn", "kronos_server:app", "--host", "0.0.0.0", "--port", "8090"]
