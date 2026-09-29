import os

from dotenv import load_dotenv

load_dotenv()


def _f(key, default):
    return float(os.getenv(key, default))


def _i(key, default):
    return int(os.getenv(key, default))


def _b(key, default):
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


class V2Settings:
    """All V2 settings. Every value can be overridden in .env with the V2_ prefix."""

    def __init__(self):
        self.api_key = os.getenv("APCA_API_KEY_ID", "")
        self.secret_key = os.getenv("APCA_API_SECRET_KEY", "")
        self.base_url = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
        self.data_feed = os.getenv("ALPACA_DATA_FEED", "iex").lower()
        self.watchlist = [s.strip().upper() for s in os.getenv("V2_WATCHLIST", "SPY,QQQ").split(",") if s.strip()]
        self.allow_shorts = _b("V2_ALLOW_SHORTS", "true")

        self.risk_per_trade_pct = _f("V2_RISK_PER_TRADE_PCT", "0.005")
        self.max_position_pct = _f("V2_MAX_POSITION_PCT", "0.20")
        self.max_positions = _i("V2_MAX_POSITIONS", "3")
        self.daily_loss_limit_pct = _f("V2_DAILY_LOSS_LIMIT_PCT", "0.02")

        self.atr_stop_mult = _f("V2_ATR_STOP_MULT", "1.5")
        self.min_stop_pct = _f("V2_MIN_STOP_PCT", "0.002")
        self.reward_risk = _f("V2_REWARD_RISK", "2.0")
        self.min_score = _i("V2_MIN_SCORE", "4")
        self.volume_surge = _f("V2_VOLUME_SURGE", "1.5")
        self.rsi_overbought = _f("V2_RSI_OVERBOUGHT", "75")
        self.rsi_oversold = _f("V2_RSI_OVERSOLD", "25")

        self.opening_range_min = _i("V2_OPENING_RANGE_MIN", "15")
        self.no_trade_open_min = _i("V2_NO_TRADE_OPEN_MIN", "5")
        self.no_new_entries_before_close_min = _i("V2_NO_NEW_ENTRIES_BEFORE_CLOSE_MIN", "15")
        self.flatten_before_close_min = _i("V2_FLATTEN_BEFORE_CLOSE_MIN", "5")
        self.cooldown_min = _i("V2_COOLDOWN_MIN", "15")
        self.poll_seconds = _i("V2_POLL_SECONDS", "60")

        self.journal_path = os.getenv("V2_JOURNAL_PATH", "logs/v2_trades.csv")
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

    @property
    def is_paper(self):
        return "paper" in self.base_url.lower()
