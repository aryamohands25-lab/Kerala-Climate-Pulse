"""logger.py – One consistent log format for every module."""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger; configure the root handler once on first use."""
    global _CONFIGURED
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
        )
        root = logging.getLogger()
        root.handlers = [handler]
        root.setLevel(logging.INFO)
        _CONFIGURED = True
    return logging.getLogger(name)
