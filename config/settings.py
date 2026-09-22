from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseModel):
    api_key_id: str = Field(default_factory=lambda: os.getenv("APCA_API_KEY_ID", ""))
    api_secret_key: str = Field(default_factory=lambda: os.getenv("APCA_API_SECRET_KEY", ""))
    api_base_url: str = Field(default_factory=lambda: os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets"))
    trading_mode: Literal["paper", "live"] = Field(default_factory=lambda: os.getenv("TRADING_MODE", "paper").lower())
    data_feed: Literal["iex", "sip"] = Field(default_factory=lambda: os.getenv("ALPACA_DATA_FEED", "iex").lower())
    watchlist: tuple[str, ...] = Field(default_factory=lambda: tuple(s.strip().upper() for s in os.getenv("WATCHLIST", "SPY,QQQ").split(",") if s.strip()))
    fast_ema_period: int = Field(default_factory=lambda: int(os.getenv("FAST_EMA_PERIOD", "9")), ge=2)
    slow_ema_period: int = Field(default_factory=lambda: int(os.getenv("SLOW_EMA_PERIOD", "21")), ge=3)
    volume_lookback: int = Field(default_factory=lambda: int(os.getenv("VOLUME_LOOKBACK", "20")), ge=2)
    volume_multiplier: float = Field(default_factory=lambda: float(os.getenv("VOLUME_MULTIPLIER", "1.20")), gt=0)
    min_bars_required: int = Field(default_factory=lambda: int(os.getenv("MIN_BARS_REQUIRED", "30")), ge=25)
    warmup_bars: int = Field(default_factory=lambda: int(os.getenv("WARMUP_BARS", "120")), ge=30, le=10000)
    max_allocation_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_ALLOCATION_PCT", "0.10")), gt=0, le=1)
    max_trade_dollars: float = Field(default_factory=lambda: float(os.getenv("MAX_TRADE_DOLLARS", "2500")), gt=0)
    max_daily_drawdown_pct: float = Field(default_factory=lambda: float(os.getenv("MAX_DAILY_DRAWDOWN_PCT", "0.02")), gt=0, le=1)
    max_positions: int = Field(default_factory=lambda: int(os.getenv("MAX_POSITIONS", "2")), ge=1)
    max_gross_leverage: float = Field(default_factory=lambda: float(os.getenv("MAX_GROSS_LEVERAGE", "1.0")), gt=0, le=1)
    stop_loss_pct: float = Field(default_factory=lambda: float(os.getenv("STOP_LOSS_PCT", "0.0075")), gt=0, lt=1)
    take_profit_pct: float = Field(default_factory=lambda: float(os.getenv("TAKE_PROFIT_PCT", "0.015")), gt=0, lt=5)
    close_intraday_positions: bool = Field(default_factory=lambda: os.getenv("CLOSE_INTRADAY_POSITIONS", "true").lower() in {"1", "true", "yes", "on"})
    state_directory: Path = Field(default_factory=lambda: PROJECT_ROOT / os.getenv("STATE_DIRECTORY", "runtime"))
    log_directory: Path = Field(default_factory=lambda: PROJECT_ROOT / os.getenv("LOG_DIRECTORY", "logs"))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    @field_validator("watchlist")
    @classmethod
    def validate_watchlist(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("WATCHLIST must contain at least one symbol.")
        if len(set(value)) != len(value):
            raise ValueError("WATCHLIST cannot contain duplicate symbols.")
        return value

    @model_validator(mode="after")
    def validate_configuration(self) -> "Settings":
        if self.trading_mode == "paper" and "paper-api.alpaca.markets" not in self.api_base_url:
            raise ValueError("Paper mode requires https://paper-api.alpaca.markets.")
        if self.trading_mode == "live" and "paper-api.alpaca.markets" in self.api_base_url:
            raise ValueError("Live mode requires https://api.alpaca.markets.")
        if self.fast_ema_period >= self.slow_ema_period:
            raise ValueError("FAST_EMA_PERIOD must be less than SLOW_EMA_PERIOD.")
        required = max(self.slow_ema_period + 2, self.volume_lookback + 2)
        if self.min_bars_required < required:
            raise ValueError(f"MIN_BARS_REQUIRED must be at least {required}.")
        if self.warmup_bars < self.min_bars_required:
            raise ValueError("WARMUP_BARS must be at least MIN_BARS_REQUIRED.")
        return self

    @property
    def paper(self) -> bool:
        return self.trading_mode == "paper"

    def ensure_directories(self) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        self.log_directory.mkdir(parents=True, exist_ok=True)

    def validate_credentials(self) -> None:
        values = {"APCA_API_KEY_ID": self.api_key_id, "APCA_API_SECRET_KEY": self.api_secret_key}
        missing = [key for key, value in values.items() if not value or value.startswith("replace_with")]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def configure_logging(settings: Settings) -> None:
    settings.ensure_directories()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(settings.log_directory / "trading_bot.log", encoding="utf-8")],
        force=True,
    )


def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
