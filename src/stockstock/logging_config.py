"""구조화 로깅 설정.

structlog 기반으로 JSON 로깅을 구성하며,
민감 정보(API 키, 토큰 등)를 자동으로 마스킹합니다.
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

# 민감 정보 마스킹 대상 키 패턴
_SENSITIVE_KEYS = re.compile(
    r"(key|secret|token|password|authorization|credential)", re.IGNORECASE
)
_MASK = "********"


def _mask_sensitive_data(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """로그 이벤트에서 민감 정보를 마스킹합니다."""
    for key, value in list(event_dict.items()):
        if _SENSITIVE_KEYS.search(key) and isinstance(value, str):
            event_dict[key] = _MASK
    return event_dict


def setup_logging(level: str = "INFO", log_file: str | None = None,
                  max_bytes: int = 10_485_760, backup_count: int = 5) -> None:
    """로깅 시스템을 초기화합니다."""

    # 표준 logging 핸들러 설정
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                log_path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
        )

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )

    # structlog 설정
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            _mask_sensitive_data,
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """이름이 지정된 로거를 반환합니다."""
    return structlog.get_logger(name)
