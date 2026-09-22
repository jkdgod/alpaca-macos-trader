# Alpaca macOS Trader

A paper-first, macOS-native algorithmic trading daemon for Python 3.12+. It uses Alpaca for execution and market data, a 9/21 EMA crossover with volume confirmation, native bracket orders, session-aware scheduling, and hard client-side risk controls.

> This software is for education and paper-trading validation. It is not investment advice and does not guarantee profitability. Keep `TRADING_MODE=paper` until you have tested every operating and failure path yourself.

## What it does

- Streams real-time minute bars for the configured watchlist.
- Warms up minute-bar history before evaluating live signals.
- Enters long positions only on a 9/21 EMA bullish cross with volume confirmation.
- Exits a long position on a bearish EMA cross.
- Requires a broker-native bracket order containing stop-loss and take-profit legs for every entry.
- Enforces allocation, dollar, position-count, and no-margin-debt leverage boundaries before entry.
- Cancels open orders, requests liquidation, and freezes the session if daily drawdown reaches the configured threshold.
- Uses the Alpaca exchange calendar for trading-day, early-close, and session-state decisions.
- Cancels orders and can close only watchlist positions at the pre-close flush.
- Uses deterministic client order IDs to reduce duplicate order risk.

## Safety boundaries

| Setting | Default | Effect |
|---|---:|---|
| `TRADING_MODE` | `paper` | Uses Alpaca paper trading by default |
| `MAX_ALLOCATION_PCT` | 0.10 | Limits one entry to 10 percent of equity |
| `MAX_TRADE_DOLLARS` | 2500.00 | Fixed dollar ceiling for one entry |
| `MAX_DAILY_DRAWDOWN_PCT` | 0.02 | Freezes execution and triggers flattening at 2 percent daily loss |
| `MAX_POSITIONS` | 2 | Limits simultaneous positions |
| `MAX_GROSS_LEVERAGE` | 1.00 | Caps gross exposure at account equity |
| `STOP_LOSS_PCT` | 0.0075 | Sets the protective stop 0.75 percent below entry |
| `TAKE_PROFIT_PCT` | 0.0150 | Sets the profit target 1.5 percent above entry |

## Install on macOS

```bash
git clone https://github.com/jkdgod/alpaca-macos-trader.git
cd alpaca-macos-trader
chmod +x setup.sh
./setup.sh
```

The setup script requires `python3.12`. If it is unavailable:

```bash
brew install python@3.12
```

## Configure paper access

`setup.sh` copies `.env.example` to `.env`. Edit `.env` locally and use only your Alpaca paper credentials:

```dotenv
APCA_API_KEY_ID=your_paper_key_id
APCA_API_SECRET_KEY=your_paper_secret_key
APCA_API_BASE_URL=https://paper-api.alpaca.markets
TRADING_MODE=paper
```

Do not commit `.env`. It is intentionally excluded through `.gitignore`.

## Validate before running

Run the unit tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Validate credentials, account access, exchange-calendar access, and risk state:

```bash
.venv/bin/python main.py healthcheck
```

Run manually in paper mode before registering the background daemon:

```bash
.venv/bin/python main.py run
```

Watch application output:

```bash
tail -f logs/trading_bot.log
```

## Emergency kill switch

The kill command freezes new execution, cancels open orders, and requests broker-side liquidation. Verify actual orders and positions in the Alpaca dashboard after using it.

```bash
.venv/bin/python main.py kill
```

## Session behavior

The scheduler uses Alpaca market-calendar data and America/New_York time.

| State | Timing | Action |
|---|---|---|
| Pre-market | 15 minutes before the scheduled open | Connect, set daily equity baseline, warm bar history |
| Market open | Scheduled open until the pre-close cutoff | Stream bars and run the strategy |
| Pre-close flush | Normally 15:55 ET | Stop strategy, cancel orders, and close watchlist positions when enabled |
| Closed | All other times | Stop the stream and sleep until the next pre-market trigger |

## macOS launchd deployment

Do this only after you have successfully run manual paper-trading checks.

```bash
PROJECT_DIR="$HOME/alpaca-macos-trader"
MACOS_LOG_DIR="$HOME/Library/Logs/TradingBot"
mkdir -p "$MACOS_LOG_DIR"

sed -e "s|__PROJECT_DIR__|$PROJECT_DIR|g" \
    -e "s|__MACOS_LOG_DIR__|$MACOS_LOG_DIR|g" \
    "$PROJECT_DIR/deployment/com.autotrade.daemon.plist" \
    > "$HOME/Library/LaunchAgents/com.autotrade.daemon.plist"

plutil -lint "$HOME/Library/LaunchAgents/com.autotrade.daemon.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.autotrade.daemon.plist"
launchctl kickstart -k "gui/$(id -u)/com.autotrade.daemon"
```

Monitor service logs:

```bash
tail -f "$MACOS_LOG_DIR/autotrade.stdout.log"
tail -f "$MACOS_LOG_DIR/autotrade.stderr.log"
```

Unload the daemon:

```bash
launchctl bootout "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.autotrade.daemon.plist"
```

## Live mode

Live trading can lose money quickly. Do not enable it until you have reviewed the code, completed paper tests, and understand the broker and strategy behavior. To deliberately switch endpoints, change both local `.env` settings:

```dotenv
TRADING_MODE=live
APCA_API_BASE_URL=https://api.alpaca.markets
```

The configuration rejects paper/live endpoint mismatches.

## Operational limits

- Broker, market-data, network, partial-fill, rejected-order, and process failures can occur.
- The circuit breaker and kill switch send requests to the broker; always confirm actual order and position state in Alpaca.
- This project does not include backtesting, slippage modeling, tax handling, or suitability analysis.
