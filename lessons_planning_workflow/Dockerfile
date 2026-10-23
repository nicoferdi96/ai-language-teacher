# syntax=docker/dockerfile:1

# --- Builder: resolve and install dependencies into a virtualenv with uv -----
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install only the locked dependencies first so this layer stays cached when
# application code changes. The project itself is run from source (uvicorn
# imports app.py directly), so it is not installed as a package.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# --- Runtime: slim image with the prebuilt virtualenv and the source ---------
FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY . /app

# Put the virtualenv first on PATH so `uvicorn` resolves to the installed one.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# The slim image ships no curl; probe the root route with the stdlib instead.
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/').status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
