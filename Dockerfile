FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY config/ ./config/
COPY tests/ ./tests/

# Default config (can be overridden via volume mount)
RUN cp config/config.example.json config/config.json 2>/dev/null || true

ENV PYTHONUNBUFFERED=1

CMD ["python", "scripts/run_orchestrator.py"]
