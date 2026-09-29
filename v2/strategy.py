from dataclasses import dataclass, field

import numpy as np

from .indicators import NY, add_indicators, regular_hours, resample
from .patterns import candle_patterns


@dataclass
class Signal:
    symbol: str
    side: str  # "long" or "short"
    score: int
    entry: float
    stop: float
    target: float
    reasons: list = field(default_factory=list)


def _trend(df):
    if len(df) < 22:
        return 0
    r = df.iloc[-1]
    if r["ema_fast"] > r["ema_slow"] and r["close"] > r["ema_slow"]:
        return 1
    if r["ema_fast"] < r["ema_slow"] and r["close"] < r["ema_slow"]:
        return -1
    return 0


def evaluate(symbol, bars, settings):
    """Score long and short setups on the latest 1-minute bar. Returns a Signal or None."""
    bars = regular_hours(bars)
    if bars is None or len(bars) < 60:
        return None

    df1 = add_indicators(bars)
    df5 = add_indicators(resample(bars, "5min"))
    df15 = add_indicators(resample(bars, "15min"))
    if len(df5) < 15:
        return None

    dates = np.asarray(df1.index.tz_convert(NY).date)
    today = dates[-1]
    today_bars = df1[dates == today]
    if len(today_bars) < settings.opening_range_min:
        return None
    opening = today_bars.iloc[: settings.opening_range_min]
    or_high, or_low = opening["high"].max(), opening["low"].min()

    prior = df1[dates < today]
    pdh = pdl = None
    if len(prior):
        prior_dates = dates[dates < today]
        last_day = prior[prior_dates == prior_dates.max()]
        pdh, pdl = last_day["high"].max(), last_day["low"].min()

    last = df1.iloc[-1]
    price = float(last["close"])
    t15, t5 = _trend(df15), _trend(df5)
    pats = candle_patterns(df1)
    rsi_now = float(last["rsi"])
    vol_surge = last["vol_avg"] > 0 and last["volume"] > settings.volume_surge * last["vol_avg"]

    long_r, short_r = [], []
    if t15 == 1:
        long_r.append("15m uptrend")
    if t15 == -1:
        short_r.append("15m downtrend")
    if t5 == 1:
        long_r.append("5m uptrend")
    if t5 == -1:
        short_r.append("5m downtrend")
    if price > last["vwap"]:
        long_r.append("above VWAP")
    if price < last["vwap"]:
        short_r.append("below VWAP")
    long_r += pats["bullish"]
    short_r += pats["bearish"]
    if vol_surge:
        (long_r if last["close"] > last["open"] else short_r).append("volume surge")
    if price > or_high:
        long_r.append("opening-range breakout")
    if price < or_low:
        short_r.append("opening-range breakdown")
    if pdh is not None and price > pdh:
        long_r.append("above prior-day high")
    if pdl is not None and price < pdl:
        short_r.append("below prior-day low")
    if 50 <= rsi_now <= 70:
        long_r.append("RSI bullish momentum")
    if 30 <= rsi_now <= 50:
        short_r.append("RSI bearish momentum")

    long_ok = t15 == 1 and price > last["vwap"] and rsi_now < settings.rsi_overbought
    short_ok = t15 == -1 and price < last["vwap"] and rsi_now > settings.rsi_oversold

    atr5 = float(df5["atr"].iloc[-1])
    stop_dist = max(settings.atr_stop_mult * atr5, price * settings.min_stop_pct)

    candidates = []
    if long_ok and len(long_r) >= settings.min_score:
        candidates.append(("long", long_r))
    if short_ok and len(short_r) >= settings.min_score:
        candidates.append(("short", short_r))
    if not candidates:
        return None
    side, reasons = max(candidates, key=lambda c: len(c[1]))

    if side == "long":
        stop, target = price - stop_dist, price + settings.reward_risk * stop_dist
    else:
        stop, target = price + stop_dist, price - settings.reward_risk * stop_dist
    return Signal(symbol, side, len(reasons), price, stop, target, reasons)
