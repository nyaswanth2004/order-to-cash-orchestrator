"""Application entry point: run `python main.py` to start the API server."""
from __future__ import annotations

import logging
import os

import uvicorn
from fastapi import FastAPI

from api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

logger = logging.getLogger("main")

app = FastAPI(
    title="AI-Powered Multi-Agent Order-to-Cash Orchestrator",
    description=(
        "Orchestrator + specialist agents (Validation, Inventory, Risk, "
        "Invoice) processing sales orders end to end."
    ),
    version="1.0.0",
)
app.include_router(router)


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    logger.info("Starting Order-to-Cash Orchestrator API on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port, log_level="info")
