FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/netbox2prom/ /app/netbox2prom/

ENV NETBOX2PROM_CONFIG=/etc/netbox2prom/config.yml \
    POLL_INTERVAL=300 \
    ENABLE_PROMETHEUS=true \
    ENABLE_ALLOY=true \
    ENABLE_SYSLOG=false \
    LOG_LEVEL=INFO \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "netbox2prom"]
