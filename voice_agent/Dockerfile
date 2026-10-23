# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Bake the VAD and turn-detector model weights into the image.
RUN python -m tutor.worker download-files

EXPOSE 8100

# Default: the LiveKit worker. The API service overrides the command in compose.
CMD ["python", "-m", "tutor.worker", "start"]
