# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Builder: uv + зависимости (включая kurigram из git)                 │
# └─────────────────────────────────────────────────────────────────────┘
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_INSTALL_DIR=/opt/shizu/.installer/python \
    UV_CACHE_DIR=/opt/shizu/.installer/cache \
    UV_NO_CACHE=0

WORKDIR /opt/shizu

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock shizu-installer.toml ./
RUN uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python -e .

# ┌─────────────────────────────────────────────────────────────────────┐
# │ Runtime: slim, не-root пользователь, только нужное                  │
# └─────────────────────────────────────────────────────────────────────┘
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /opt/shizu

RUN groupadd -r shizu && useradd -r -g shizu -d /opt/shizu -s /usr/sbin/nologin shizu \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --chown=shizu:shizu shizu scripts start.sh install.sh pyproject.toml shizu-installer.toml ./

VOLUME ["/opt/shizu/config.ini", "/opt/shizu/data", "/opt/shizu/.config/shizu"]
USER shizu

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD pgrep -f "python -u -m shizu" >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash", "start.sh"]
