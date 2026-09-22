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

    def test_enters_on_bullish_cross_with_confirming_volume(self) -> None:
        bars = pd.DataFrame(
            {
                "close": [100, 99, 98, 97, 98, 99, 100, 105],
                "volume": [100, 100, 100, 100, 100, 100, 100, 150],
            },
            index=pd.date_range(
                "2026-01-02 14:30:00+00:00",
                periods=8,
                freq="min",
            ),
        )
        signal_value = self.strategy.evaluate("SPY", bars, has_position=False)
        self.assertEqual(signal_value.action, SignalAction.ENTER_LONG)
        self.assertEqual(signal_value.symbol, "SPY")

    def test_exits_on_bearish_cross_when_long(self) -> None:
        bars = pd.DataFrame(
            {
                "close": [105, 104, 103, 102, 101, 100, 99, 95],
                "volume": [100] * 8,
            },
            index=pd.date_range(
                "2026-01-02 14:30:00+00:00",
                periods=8,
                freq="min",
            ),
        )
        signal_value = self.strategy.evaluate("SPY", bars, has_position=True)
        self.assertEqual(signal_value.action, SignalAction.EXIT_LONG)
        self.assertEqual(signal_value.symbol, "SPY")

    def test_holds_without_required_history(self) -> None:
        bars = pd.DataFrame(
            {"close": [100, 101], "volume": [100, 100]},
            index=pd.date_range(
                "2026-01-02 14:30:00+00:00",
                periods=2,
                freq="min",
            ),
        )
        signal_value = self.strategy.evaluate("SPY", bars, has_position=False)
        self.assertEqual(signal_value.action, SignalAction.HOLD)


if __name__ == "__main__":
    unittest.main()
