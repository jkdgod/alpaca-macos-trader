"""V2 long/short bot. Usage: python main_v2.py [healthcheck|run|flatten]"""
import argparse
import logging
import os
import sys

from v2.config import V2Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["healthcheck", "run", "flatten"])
    args = parser.parse_args()

    s = V2Settings()
    logging.basicConfig(level=s.log_level, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    if not s.is_paper and os.getenv("V2_ALLOW_LIVE", "false").lower() != "true":
        print("Refusing to start: V2 runs on the PAPER endpoint only.")
        return 2
    if not s.api_key or not s.secret_key:
        print("Missing APCA_API_KEY_ID / APCA_API_SECRET_KEY in .env")
        return 2

    from v2.broker import Broker
    from v2.engine import EngineV2

    b = Broker(s)
    if args.command == "healthcheck":
        acct = b.account()
        clock = b.clock()
        print(f"Mode: {'paper' if s.is_paper else 'LIVE'}")
        print(f"Equity: ${float(acct.equity):,.2f}")
        print(f"Shorting enabled: {acct.shorting_enabled}")
        print(f"Market open: {clock.is_open}  next open: {clock.next_open}  next close: {clock.next_close}")
        for sym in s.watchlist:
            bars = b.bars(sym)
            print(f"{sym}: bars={len(bars)} easy-to-borrow={b.can_short(sym)}")
        return 0
    if args.command == "flatten":
        b.flatten()
        return 0
    EngineV2(s, b).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
