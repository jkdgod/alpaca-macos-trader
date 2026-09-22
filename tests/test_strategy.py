from __future__ import annotations

import unittest

import pandas as pd

from strategy.strategy import EmaVolumeCrossStrategy, SignalAction


class StrategyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = EmaVolumeCrossStrategy(
            fast_period=3,
            slow_period=5,
            volume_lookback=3,
            volume_multiplier=1.10,
            min_bars_required=8,
        )

    @staticmethod
    def make_bars(closes: list[float], volumes: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {"close": closes, "volume": volumes},
            index=pd.date_range(
                "2026-01-02 14:30:00+00:00",
                periods=len(closes),
                freq="min",
            ),
        )

    def test_enters_on_bullish_cross_with_confirming_volume(self) -> None:
        bars = self.make_bars(
            closes=[100, 99, 98, 97, 96, 96, 96, 104],
            volumes=[100, 100, 100, 100, 100, 100, 100, 150],
        )

        signal_value = self.strategy.evaluate("SPY", bars, has_position=False)

        self.assertEqual(signal_value.action, SignalAction.ENTER_LONG)
        self.assertEqual(signal_value.symbol, "SPY")
        self.assertEqual(signal_value.price, 104.0)

    def test_exits_on_bearish_cross_when_long(self) -> None:
        bars = self.make_bars(
            closes=[100, 101, 102, 103, 104, 104, 104, 96],
            volumes=[100, 100, 100, 100, 100, 100, 100, 100],
        )

        signal_value = self.strategy.evaluate("SPY", bars, has_position=True)

        self.assertEqual(signal_value.action, SignalAction.EXIT_LONG)
        self.assertEqual(signal_value.symbol, "SPY")
        self.assertEqual(signal_value.price, 96.0)

    def test_holds_without_required_history(self) -> None:
        bars = self.make_bars(
            closes=[100, 101],
            volumes=[100, 100],
        )

        signal_value = self.strategy.evaluate("SPY", bars, has_position=False)

        self.assertEqual(signal_value.action, SignalAction.HOLD)


if __name__ == "__main__":
    unittest.main()
