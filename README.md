# Alpaca macOS Trader

Paper-first, macOS-native algorithmic trading daemon for Python 3.12+.

## Safety

- Paper mode is the default.
- Keep real API credentials only in your local `.env` file.
- `.env` is excluded from Git.
- Validate the strategy, account connectivity, order behavior, and kill switch in paper mode before considering live trading.

## Install

```bash
git clone https://github.com/jkdgod/alpaca-macos-trader.git
cd alpaca-macos-trader
chmod +x setup.sh
./setup.sh
```

Then edit `.env` with Alpaca paper credentials and run:

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python main.py healthcheck
```

## Operating commands

```bash
.venv/bin/python main.py run
.venv/bin/python main.py healthcheck
.venv/bin/python main.py kill
```

The `kill` command freezes local execution, cancels open orders, and requests broker-side liquidation. Verify results in the Alpaca dashboard.
