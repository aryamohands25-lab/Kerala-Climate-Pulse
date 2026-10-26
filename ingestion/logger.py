"""
logger.py – Shared structured logger used by every module.

Usage:
    from ingestion.logger import get_logger
    log = get_logger(__name__)
    log.info("Fetching data", district="Kozhikode")
"""
from __future__ import annotations

import logging
import sys
from typing import Any


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Return a configured logger with a rich, human-readable format."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
