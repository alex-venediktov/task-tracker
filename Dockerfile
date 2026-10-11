# Служба трекера задач: REST, сырой markdown и MCP на одном порту.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TT_DATA_DIR=/data TT_HOST=0.0.0.0 TT_PORT=8113

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
# Зависимости отдельным слоем до кода.
RUN mkdir -p tracker && touch tracker/__init__.py && pip install . && rm -rf tracker
COPY tracker ./tracker
RUN pip install --no-deps . && rm -rf /app/tracker

VOLUME /data
EXPOSE 8113
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS "http://localhost:${TT_PORT}/healthz" || exit 1

CMD ["tracker"]
