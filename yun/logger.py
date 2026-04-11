from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional


LOG_NAME = "yunlin_bus"
DEFAULT_LOG_LEVEL = os.getenv("YUNLIN_BUS_LOG_LEVEL", "INFO").upper()
DEFAULT_LOG_DIR = Path(os.getenv("YUNLIN_BUS_LOG_DIR", "logs"))
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "app.log"


def _safe_json(data: dict[str, Any]) -> str:
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception as exc:
        return json.dumps(
            {
                "logger_error": "json_serialize_failed",
                "exception": str(exc),
                "raw": str(data),
            },
            ensure_ascii=False,
            default=str,
        )


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _ensure_log_dir() -> None:
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _build_stream_handler() -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setFormatter(_build_formatter())
    return handler


def _build_file_handler() -> logging.Handler:
    _ensure_log_dir()
    handler = logging.FileHandler(DEFAULT_LOG_FILE, encoding="utf-8")
    handler.setFormatter(_build_formatter())
    return handler


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOG_NAME)

    if logger.handlers:
        return logger

    logger.setLevel(DEFAULT_LOG_LEVEL)
    logger.propagate = False

    logger.addHandler(_build_stream_handler())
    logger.addHandler(_build_file_handler())

    return logger


logger = get_logger()


def log_debug(message: str, payload: Optional[dict[str, Any]] = None) -> None:
    if payload is None:
        logger.debug(message)
        return
    logger.debug("%s %s", message, _safe_json(payload))


def log_info(message: str, payload: Optional[dict[str, Any]] = None) -> None:
    if payload is None:
        logger.info(message)
        return
    logger.info("%s %s", message, _safe_json(payload))


def log_warning(message: str, payload: Optional[dict[str, Any]] = None) -> None:
    if payload is None:
        logger.warning(message)
        return
    logger.warning("%s %s", message, _safe_json(payload))


def log_error(
    message: str,
    payload: Optional[dict[str, Any]] = None,
    exc: Optional[Exception] = None,
) -> None:
    if payload is None:
        payload = {}

    if exc is not None:
        payload = dict(payload)
        payload["exception"] = str(exc)
        logger.error("%s %s", message, _safe_json(payload), exc_info=True)
        return

    logger.error("%s %s", message, _safe_json(payload))


def log_request(event: str, payload: dict[str, Any]) -> None:
    logger.info("request %s %s", event, _safe_json(payload))


def log_router_decision(payload: dict[str, Any]) -> None:
    logger.info("router_decision %s", _safe_json(payload))


def log_result(payload: dict[str, Any]) -> None:
    logger.info("result %s", _safe_json(payload))


def log_state(event: str, payload: dict[str, Any]) -> None:
    logger.info("state %s %s", event, _safe_json(payload))