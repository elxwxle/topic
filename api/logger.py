import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


LOG_NAME = "yunlin_bus_api"
DEFAULT_LOG_LEVEL_NAME = os.getenv("YUNLIN_BUS_LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_LEVEL = getattr(logging, DEFAULT_LOG_LEVEL_NAME, logging.INFO)

DEFAULT_LOG_DIR = Path(os.getenv("YUNLIN_BUS_LOG_DIR", "logs"))
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / os.getenv("YUNLIN_BUS_LOG_FILE", "app.log")

LOG_TO_FILE = os.getenv("YUNLIN_BUS_LOG_TO_FILE", "1") == "1"
LOG_MAX_BYTES = int(os.getenv("YUNLIN_BUS_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("YUNLIN_BUS_LOG_BACKUP_COUNT", "3"))


def _ensure_log_dir() -> None:
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_stream_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(_build_formatter())
    return handler


def _build_file_handler() -> logging.Handler:
    _ensure_log_dir()
    handler = RotatingFileHandler(
        DEFAULT_LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(_build_formatter())
    return handler


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOG_NAME)

    if logger.handlers:
        return logger

    logger.setLevel(DEFAULT_LOG_LEVEL)
    logger.propagate = False

    logger.addHandler(_build_stream_handler())

    if LOG_TO_FILE:
        logger.addHandler(_build_file_handler())

    return logger


def log_request(event: str, payload: dict[str, Any]) -> None:
    logger = get_logger()
    logger.info("request | %s | %s", event, payload)


def log_router_decision(payload: dict[str, Any]) -> None:
    logger = get_logger()
    logger.info("router_decision | %s", payload)


def log_result(payload: dict[str, Any]) -> None:
    logger = get_logger()
    logger.info("result | %s", payload)