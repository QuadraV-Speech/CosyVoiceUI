import contextvars
import logging
import os
import sys
import uuid
from logging.handlers import RotatingFileHandler

from .config import (
    LOG_BACKUP_COUNT,
    LOG_FILE,
    LOG_LEVEL,
    LOG_MAX_BYTES,
)


request_id_ctx = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str):
    return request_id_ctx.set(request_id or new_request_id())


def reset_request_id(token) -> None:
    request_id_ctx.reset(token)


def setup_logging() -> None:
    root = logging.getLogger()
    if getattr(root, "_cosyvoice_configured", False):
        return

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(process)d:%(threadName)s] "
        "[%(request_id)s] %(name)s - %(message)s"
    )
    request_filter = RequestIdFilter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_filter)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(request_filter)

    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(level)

    for logger_name in ("httpx", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    root._cosyvoice_configured = True
