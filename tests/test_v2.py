import unittest

import numpy as np
import pandas as pd

from v2.config import V2Settings
from v2.indicators import add_indicators, regular_hours, rsi
from v2.patterns import candle_patterns
from v2.risk import DailyRisk, position_size
from v2.strategy import evaluate


def make_bars(days=3, drift=0.02, seed=1):
    rng = np.random.default_rng(seed)
    frames = []
    for d in range(days):
        start = pd.Timestamp("2026-09-21 13:30", tz="UTC") + pd.Timedelta(days=d)
        frames.append(pd.date_range(start, periods=390, freq="1min"))
    idx = frames[0].append(frames[1:])
    n = len(idx)
    close = 100 + np.cumsum(drift + rng.normal(0, 0.05, n))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + 0.03
    low = np.minimum(open_, close) - 0.03
    vol = rng.integers(1000, 3000, n).astype(float)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


class V2Tests(unittest.TestCase):
    def setUp(self):
        self.s = V2Settings()

    def test_bullish_engulfing(self):
        df = pd.DataFrame({"open": [10.5, 9.8], "high": [10.6, 10.9], "low": [9.9, 9.7], "close": [10.0, 10.8],
                           "volume": [1, 1]})
        self.assertIn("bullish engulfing", candle_patterns(df)["bullish"])

    def test_bearish_engulfing(self):
        df = pd.DataFrame({"open": [10.0, 10.8], "high": [10.6, 10.9], "low": [9.9, 9.7], "close": [10.5, 9.8],
                           "volume": [1, 1]})
        self.assertIn("bearish engulfing", candle_patterns(df)["bearish"])

    def test_rsi_in_range(self):
        r = rsi(make_bars()["close"])
        self.assertTrue(((r >= 0) & (r <= 100)).all())

    def test_position_size_limits_risk(self):
        qty = position_size(100000, 100.0, 99.0, self.s)
        self.assertLessEqual(qty * 1.0, 100000 * self.s.risk_per_trade_pct)
        self.assertLessEqual(qty * 100.0, 100000 * self.s.max_position_pct + 1e-6)

    def test_daily_loss_freeze(self):
        r = DailyRisk(0.02)
        self.assertFalse(r.update("d1", 100000))
        self.assertTrue(r.update("d1", 97900))
        self.assertFalse(r.update("d2", 97900))

    def test_uptrend_never_signals_short(self):
        sig = evaluate("TEST", make_bars(drift=0.03), self.s)
        if sig is not None:
            self.assertEqual(sig.side, "long")
            self.assertLess(sig.stop, sig.entry)
            self.assertGreater(sig.target, sig.entry)

    def test_downtrend_never_signals_long(self):
        sig = evaluate("TEST", make_bars(drift=-0.03), self.s)
        if sig is not None:
            self.assertEqual(sig.side, "short")
            self.assertGreater(sig.stop, sig.entry)
            self.assertLess(sig.target, sig.entry)

    def test_regular_hours_filter(self):
        bars = make_bars(days=1)
        self.assertEqual(len(regular_hours(bars)), 390)

    def test_indicators_columns(self):
        out = add_indicators(make_bars(days=1))
        for col in ["ema_fast", "ema_slow", "rsi", "atr", "vwap", "vol_avg"]:
            self.assertIn(col, out.columns)


if __name__ == "__main__":
    unittest.main()
