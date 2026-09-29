from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
OHLCV = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}


def regular_hours(df):
    """Keep only 9:30-16:00 New York bars."""
    if df.empty:
        return df
    ny = df.index.tz_convert(NY)
    minutes = np.asarray(ny.hour) * 60 + np.asarray(ny.minute)
    return df[(minutes >= 570) & (minutes < 960)]


def resample(df, rule):
    return df.resample(rule).agg(OHLCV).dropna()


def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()


def rsi(series, n=14):
    delta = series.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(down != 0, 100.0).fillna(50.0)


def atr(df, n=14):
    prev_close = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def vwap(df):
    """Session VWAP that resets every New York trading day."""
    days = np.asarray(df.index.tz_convert(NY).date)
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = (typical * df["volume"]).groupby(days).cumsum()
    vol = df["volume"].groupby(days).cumsum().replace(0, np.nan)
    return (pv / vol).fillna(df["close"])


def add_indicators(df, fast=9, slow=21):
    out = df.copy()
    out["ema_fast"] = ema(out["close"], fast)
    out["ema_slow"] = ema(out["close"], slow)
    out["rsi"] = rsi(out["close"])
    out["atr"] = atr(out)
    out["vwap"] = vwap(out)
    out["vol_avg"] = out["volume"].rolling(20, min_periods=5).mean()
    return out
