import math


def position_size(equity, price, stop, settings):
    """Shares to trade so that hitting the stop loses about risk_per_trade_pct of equity."""
    dist = abs(price - stop)
    if dist <= 0 or price <= 0 or equity <= 0:
        return 0
    by_risk = math.floor(equity * settings.risk_per_trade_pct / dist)
    by_cap = math.floor(equity * settings.max_position_pct / price)
    return max(0, min(by_risk, by_cap))


class DailyRisk:
    """Freezes new trading for the day once the daily loss limit is hit."""

    def __init__(self, limit_pct):
        self.limit_pct = limit_pct
        self.date = None
        self.start_equity = None
        self.frozen = False

    def update(self, date, equity):
        if date != self.date:
            self.date, self.start_equity, self.frozen = date, equity, False
        if self.start_equity and (self.start_equity - equity) / self.start_equity >= self.limit_pct:
            self.frozen = True
        return self.frozen

    def drawdown_pct(self, equity):
        if not self.start_equity:
            return 0.0
        return (self.start_equity - equity) / self.start_equity
