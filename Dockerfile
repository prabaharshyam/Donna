# Donna: personal assistant. One container, one persistent volume mounted at /data.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Kolkata \
    DONNA_DATA=/data \
    DONNA_CLOUD=1

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server ./server
COPY web ./web

EXPOSE 8765
# --proxy-headers: the platform's HTTPS proxy forwards the real scheme/IP (secure cookies, HSTS).
# Run a single instance only: the scheduler and Telegram bot must not run twice.
CMD exec uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8765} --proxy-headers --forwarded-allow-ips="*"
