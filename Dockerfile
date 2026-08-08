FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir -e ".[dev]"

RUN mkdir -p /root/.vsrs/logs /root/.vsrs/worktrees

ENV VSRS_DB_PATH=/data/vsrs.db
ENV VSRS_LOG_DIR=/root/.vsrs/logs
ENV VSRS_SANDBOX_WORKTREE_DIR=/root/.vsrs/worktrees

VOLUME ["/data"]

ENTRYPOINT ["vsrs"]
CMD ["--help"]
