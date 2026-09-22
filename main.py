from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from config.settings import configure_logging, get_settings
from engine import TradingEngine
from execution.broker import AlpacaBroker
from risk.risk_manager import RiskManager
from scheduling.scheduler import MarketScheduler
from strategy.strategy import EmaVolumeCrossStrategy

EASTERN = ZoneInfo("America/New_York")


def build_components():
    settings = get_settings()
    configure_logging(settings)
    settings.validate_credentials()
    broker = AlpacaBroker(settings)
    risk_manager = RiskManager(settings, broker)
    scheduler = MarketScheduler(broker)
    strategy = EmaVolumeCrossStrategy(settings.fast_ema_period, settings.slow_ema_period, settings.volume_lookback, settings.volume_multiplier, settings.min_bars_required)
    return settings, broker, risk_manager, scheduler, strategy


def healthcheck() -> int:
    settings, broker, risk_manager, scheduler, _ = build_components()
    account = broker.verify_connectivity()
    state, session = scheduler.state_at(datetime.now(EASTERN))
    print("Alpaca connectivity: OK")
    print(f"Trading mode: {settings.trading_mode}")
    print(f"Equity: ${account.equity:,.2f}")
    print(f"Buying power: ${account.buying_power:,.2f}")
    print(f"Session state: {state}")
    print(f"Session: {session}")
    print(f"Risk: {risk_manager.status(account)}")
    return 0


def kill() -> int:
    _, _, risk_manager, _, _ = build_components()
    risk_manager.emergency_kill_switch("Manual CLI kill switch")
    print("Kill switch requested. Verify positions and orders in Alpaca.")
    return 0


def run() -> int:
    settings, broker, risk_manager, scheduler, strategy = build_components()
    asyncio.run(TradingEngine(settings, broker, risk_manager, scheduler, strategy).run())
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpaca macOS trading daemon")
    parser.add_argument("command", nargs="?", default="run", choices=("run", "healthcheck", "kill"))
    return parser.parse_args()


if __name__ == "__main__":
    command = parse_args().command
    try:
        raise SystemExit({"run": run, "healthcheck": healthcheck, "kill": kill}[command]())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        logging.exception("Fatal error: %s", exc)
        raise SystemExit(1)
