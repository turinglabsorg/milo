FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv
FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY milo ./milo
COPY web ./web
COPY scripts/serve.py ./scripts/serve.py
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" MILO_CONTAINER=1 MILO_DATA=/data
USER 501:20
EXPOSE 8025 8029
CMD ["python", "scripts/serve.py"]
