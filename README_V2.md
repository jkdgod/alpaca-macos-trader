# V2 long/short intraday bot (paper only)

V2 trades both directions on 1-minute bars, confirmed by 5- and 15-minute trend.

## How it decides
A setup needs the 15-minute trend and VWAP on its side, plus at least `V2_MIN_SCORE` (default 4) of these:
- 5m and 15m trend (9/21 EMA)
- Price vs VWAP
- Candlestick patterns: engulfing, hammer, shooting star, marubozu (doji and inside bars are logged as neutral)
- Volume surge (1.5x the 20-bar average)
- Opening-range breakout or breakdown (first 15 minutes)
- Break of the prior-day high or low
- RSI momentum zone (skips longs above 75 and shorts below 25)

## Orders and risk
- Every entry is a bracket order: market entry + take-profit + stop-loss.
- Stop = 1.5x the 5-minute ATR. Target = 2x the risk.
- Risk per trade = 0.5% of equity. Position size is capped at 20% of equity.
- Max 3 positions. Daily loss limit of 2% flattens everything and stops new trades for the day.
- Shorts only when the stock is shortable and easy-to-borrow that day.
- No entries in the first 5 minutes or the last 15. Everything is flattened 5 minutes before the close.
- The bot exits on its own after the close.
- Refuses to run on a live endpoint unless `V2_ALLOW_LIVE=true`.

## Commands
```
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python main_v2.py healthcheck
.venv/bin/python backtest_v2.py SPY --days 20
.venv/bin/python main_v2.py run
.venv/bin/python main_v2.py flatten
```

## Optional .env settings
```
V2_WATCHLIST=SPY,QQQ
V2_ALLOW_SHORTS=true
V2_RISK_PER_TRADE_PCT=0.005
V2_MAX_POSITIONS=3
V2_DAILY_LOSS_LIMIT_PCT=0.02
V2_MIN_SCORE=4
```
Trades are logged to `logs/v2_trades.csv`.
