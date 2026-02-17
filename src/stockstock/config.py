"""설정 관리 모듈.

.env에서 시크릿을, config/settings.yaml에서 트레이딩 설정을 로드합니다.
모든 시크릿은 SecretStr 타입으로 보호됩니다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_project_root() -> Path:
    """프로젝트 루트 디렉토리를 결정합니다.

    환경변수 STOCKSTOCK_ROOT가 설정되어 있으면 해당 경로를 사용하고,
    아니면 현재 작업 디렉토리(CWD)를 사용합니다.
    Docker에서는 WORKDIR /app이 CWD가 됩니다.
    """
    env_root = os.environ.get("STOCKSTOCK_ROOT")
    if env_root:
        return Path(env_root)
    return Path.cwd()


PROJECT_ROOT = _resolve_project_root()


def _load_yaml_settings() -> dict[str, Any]:
    """config/settings.yaml 파일을 로드합니다."""
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    if settings_path.exists():
        with open(settings_path) as f:
            return yaml.safe_load(f) or {}
    return {}


class BrokerConfig(BaseSettings):
    """한국투자증권 KIS API 인증 설정."""

    model_config = SettingsConfigDict(env_prefix="KIS_", env_file=".env", extra="ignore")

    app_key: SecretStr
    app_secret: SecretStr
    hts_id: str
    account_number: str  # "00000000-01" 형식

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        if "-" not in v or len(v.split("-")) != 2:
            raise ValueError("계좌번호는 'XXXXXXXX-XX' 형식이어야 합니다")
        return v


class TelegramConfig(BaseSettings):
    """Telegram 봇 설정."""

    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", env_file=".env", extra="ignore")

    bot_token: SecretStr
    chat_id: str
    enabled: bool = True
    daily_summary_hour: int = 17

    @field_validator("daily_summary_hour")
    @classmethod
    def validate_daily_summary_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("daily_summary_hour는 0~23 사이여야 합니다")
        return v


class TradingConfig(BaseSettings):
    """트레이딩 설정 (settings.yaml에서 로드)."""

    model_config = SettingsConfigDict(extra="ignore")

    mode: str = "paper"
    symbols: list[str] = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN"]
    check_interval_minutes: int = 60
    max_position_pct: float = 0.10
    stop_loss_pct: float = 0.05
    max_daily_loss_usd: float = 500.0
    order_type: str = "MARKET"

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in ("paper", "live"):
            raise ValueError("mode는 'paper' 또는 'live'이어야 합니다")
        return v

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v: list[str]) -> list[str]:
        symbol_pattern = re.compile(r"^[A-Z]{1,5}$")
        for s in v:
            if not symbol_pattern.match(s):
                raise ValueError(f"유효하지 않은 심볼: '{s}' (1~5자 영문 대문자만 허용)")
        return v

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, v: str) -> str:
        if v not in ("MARKET", "LIMIT"):
            raise ValueError("order_type은 'MARKET' 또는 'LIMIT'이어야 합니다")
        return v

    @field_validator("max_position_pct")
    @classmethod
    def validate_max_position_pct(cls, v: float) -> float:
        if not 0.01 <= v <= 1.0:
            raise ValueError("max_position_pct는 0.01~1.0 사이여야 합니다")
        return v


class ModelConfig(BaseSettings):
    """ML 모델 설정."""

    model_config = SettingsConfigDict(extra="ignore")

    artifact_path: str = "models/lgbm_v1.pkl"
    confidence_threshold: float = 0.6
    lookback_days: int = 252
    retrain_interval_days: int = 30


class LoggingConfig(BaseSettings):
    """로깅 설정."""

    model_config = SettingsConfigDict(extra="ignore")

    level: str = "INFO"
    file: str = "logs/stockstock.log"
    max_bytes: int = 10_485_760  # 10MB
    backup_count: int = 5


class AppConfig:
    """전체 애플리케이션 설정을 관리하는 최상위 클래스."""

    def __init__(self) -> None:
        yaml_settings = _load_yaml_settings()

        self.broker = BrokerConfig()  # type: ignore[call-arg]
        self.trading = TradingConfig(**yaml_settings.get("trading", {}))
        self.model = ModelConfig(**yaml_settings.get("model", {}))
        self.logging = LoggingConfig(**yaml_settings.get("logging", {}))

        # Telegram: .env 시크릿은 자동 로드, yaml 설정은 생성자에 전달
        self.telegram = TelegramConfig(**yaml_settings.get("telegram", {}))  # type: ignore[call-arg]

    @property
    def is_paper_trading(self) -> bool:
        return self.trading.mode == "paper"

    @property
    def db_path(self) -> Path:
        return PROJECT_ROOT / "data" / "stockstock.db"
