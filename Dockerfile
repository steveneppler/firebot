FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STATE_PATH=/data/state.json

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY firebot ./firebot

# Persist dedupe state here; mount a Coolify volume at /data.
VOLUME ["/data"]

# Default: always-on loop. Override CMD with ["--once"] for a scheduled task.
ENTRYPOINT ["python", "-m", "firebot.main"]
CMD ["--loop"]
