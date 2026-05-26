"""
Structured logging setup for all agents.
"""
import logging
import sys
from typing import Optional
from src.config.settings import config


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a configured logger for the given agent/module name."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    effective_level = level or config.agent.log_level
    logger.setLevel(getattr(logging, effective_level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    return logger
