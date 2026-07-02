FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends syslog-ng-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/netbox2prom/ /app/netbox2prom/

ENV NETBOX2PROM_CONFIG=/etc/netbox2prom/config.yml \
    POLL_INTERVAL=300 \
    ENABLE_PROMETHEUS=true \
    ENABLE_PROBE_ICMP=true \
    ENABLE_PROBE_HTTP=true \
    ENABLE_SYSLOG=false \
    LOG_LEVEL=INFO \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "netbox2prom"]
