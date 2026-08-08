FROM node:18-slim AS dashboard-builder

WORKDIR /web-dashboard
COPY web-dashboard/package.json web-dashboard/package-lock.json ./
RUN npm ci
COPY web-dashboard/ ./
RUN npm run build

FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir -e ".[dev]"

COPY --from=dashboard-builder /web-dashboard/dist ./web-dashboard/dist

RUN mkdir -p /root/.vsrs/logs /root/.vsrs/worktrees

ENV VSRS_DB_PATH=/data/vsrs.db
ENV VSRS_LOG_DIR=/root/.vsrs/logs
ENV VSRS_SANDBOX_WORKTREE_DIR=/root/.vsrs/worktrees
# LM Studio runs on the host — use host.docker.internal to reach it
ENV VSRS_MODEL_PROVIDER=lmstudio
ENV VSRS_MODEL_BASE_URL=http://host.docker.internal:1234/v1

VOLUME ["/data"]

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "vsrs.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
