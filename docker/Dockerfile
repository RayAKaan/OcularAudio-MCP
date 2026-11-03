FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOME=/home/ocular
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates nodejs npm \
    && groupadd --gid 10001 ocular \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin ocular \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt package.json server.json ./
RUN pip install --no-cache-dir -r requirements.txt && npm install --omit=dev
COPY . .
RUN mkdir -p /home/ocular/.cache/ocular_audio_mcp /app/cache /app/batch-cache \
    && chown -R ocular:ocular /home/ocular/.cache /app/cache /app/batch-cache \
    && python -m py_compile ocular_audio_mcp.py
USER 10001:10001
EXPOSE 8000
CMD ["python", "ocular_audio_mcp.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
