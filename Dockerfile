# The SDK wheel must be in wheels/ first (see wheels/README.md). The site's AI
# cluster is arm64:
#
#   docker buildx build --platform linux/arm64 -t ameba-hello-world:v1 --load .
#   docker run --rm -p 8000:8000 --env-file .env ameba-hello-world:v1
#
FROM python:3.11-slim

# uv for fast, reproducible installs (from the official distroless uv image).
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    RELOAD=false

# the app + the SDK wheel (.dockerignore keeps .env, .venv and .git out)
WORKDIR /app
COPY . .
RUN uv sync --no-dev

# Filled in where the app is deployed (the AI Apps card, or --env-file above);
# empty here so the key is never part of the image.
ENV AMEBA_BASE_URL= \
    AMEBA_API_KEY= \
    AMEBA_LLM_MODEL=

EXPOSE 8000
# Not root. The venv uv built is used as is; nothing is written at startup.
USER 1000
CMD ["/app/.venv/bin/python", "run.py"]
