FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY src/ /app/src/

RUN groupadd --system --gid 10001 localsync \
    && useradd --system --uid 10001 --gid localsync localsync \
    && mkdir -p /data/envios /data/recibidos \
    && chown -R localsync:localsync /data

USER localsync:localsync
EXPOSE 9001

CMD ["python", "-m", "src.backend.network.p2p_socket", "--host", "0.0.0.0", "--port", "9001", "--directory", "/data/recibidos", "--on-conflict", "keep-both"]
