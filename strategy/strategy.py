from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd


class SignalAction(StrEnum):
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategySignal:
    symbol: str
    action: SignalAction
    bar_timestamp: str
    price: float
    reason: str


class EmaVolumeCrossStrategy:
    def __init__(self, fast_period: int, slow_period: int, volume_lookback: int, volume_multiplier: float, min_bars_required: int) -> None:
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.volume_lookback = volume_lookback
        self.volume_multiplier = volume_multiplier
        self.min_bars_required = min_bars_required

    def evaluate(self, symbol: str, bars: pd.DataFrame, has_position: bool) -> StrategySignal:
        if len(bars) < self.min_bars_required:
            return StrategySignal(symbol, SignalAction.HOLD, "", 0.0, "Insufficient bar history.")
        frame = bars.sort_index().copy()
        fast = frame["close"].ewm(span=self.fast_period, adjust=False).mean()
        slow = frame["close"].ewm(span=self.slow_period, adjust=False).mean()
        prior_volume = float(frame["volume"].iloc[-(self.volume_lookback + 1):-1].mean())
        current_volume = float(frame["volume"].iloc[-1])
        volume_confirmed = prior_volume > 0 and current_volume >= prior_volume * self.volume_multiplier
        bullish_cross = float(fast.iloc[-2]) <= float(slow.iloc[-2]) and float(fast.iloc[-1]) > float(slow.iloc[-1])
        bearish_cross = float(fast.iloc[-2]) >= float(slow.iloc[-2]) and float(fast.iloc[-1]) < float(slow.iloc[-1])
        timestamp = str(frame.index[-1])
        price = float(frame["close"].iloc[-1])
        if not has_position and bullish_cross and volume_confirmed:
            return StrategySignal(symbol, SignalAction.ENTER_LONG, timestamp, price, f"Bullish EMA cross with volume confirmation ({current_volume:.0f} vs {prior_volume:.0f}).")
        if has_position and bearish_cross:
            return StrategySignal(symbol, SignalAction.EXIT_LONG, timestamp, price, "Bearish EMA cross.")
        return StrategySignal(symbol, SignalAction.HOLD, timestamp, price, "No actionable signal.")
