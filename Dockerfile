# The app resolves the SDK from this repo's wheels/ folder (download the
# wheel first; see wheels/README.md):
#
#   docker build -t ameba-hello-world:v1 .
#   docker run --rm -p 8000:8000 --env-file .env ameba-hello-world:v1
#
FROM python:3.11-slim

# uv for fast, reproducible installs (from the official distroless uv image).
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    RELOAD=false

# the app + the SDK wheel (path-dependency target wheels/*.whl)
WORKDIR /app
COPY . .
RUN uv sync --no-dev

EXPOSE 8000
# --no-sync: run the already-built prod-only env; don't re-sync at startup.
CMD ["uv", "run", "--no-sync", "python", "run.py"]
