"""Entrypoint — ``uv run python run.py`` (or ``uvicorn main:app --reload``).

Reads AMEBA_BASE_URL / AMEBA_API_KEY from the environment (or a .env file, or
~/.ameba/credentials.json). Host/port via HOST / PORT env.
"""
from __future__ import annotations

import os

import uvicorn
from dotenv import load_dotenv

if __name__ == "__main__":
    load_dotenv()  # optional .env in this dir
    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        # Off by default: the container image runs this file, and the uvicorn
        # reloader has no business in a pod. Dev box: RELOAD=true (or .env).
        reload=os.environ.get("RELOAD", "false").lower() in ("1", "true", "yes"),
    )
