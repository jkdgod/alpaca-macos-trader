"""Backtest V2 on past 1-minute bars. Usage: python backtest_v2.py SPY --days 20"""
import argparse
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from v2.config import V2Settings
from v2.indicators import NY, regular_hours
from v2.risk import position_size
from v2.strategy import evaluate


def simulate(symbol, bars, s, equity=100000.0, window=1500):
    bars = regular_hours(bars)
    ny = bars.index.tz_convert(NY)
    trades, pos = [], None
    close_min = 16 * 60
    for i in range(len(bars) - 1):
        t = ny[i]
        mins = t.hour * 60 + t.minute
        bar = bars.iloc[i]
        if pos is not None:
            hit = None
            if pos["side"] == "long":
                if bar["low"] <= pos["stop"]:
                    hit = pos["stop"]
                elif bar["high"] >= pos["target"]:
                    hit = pos["target"]
            else:
                if bar["high"] >= pos["stop"]:
                    hit = pos["stop"]
                elif bar["low"] <= pos["target"]:
                    hit = pos["target"]
            if hit is None and (mins >= close_min - s.flatten_before_close_min or ny[i + 1].date() != t.date()):
                hit = bar["close"]
            if hit is not None:
                sign = 1 if pos["side"] == "long" else -1
                pnl = sign * (hit - pos["entry"]) * pos["qty"]
                equity += pnl
                trades.append({**pos, "exit": hit, "exit_time": t, "pnl": pnl,
                               "r": sign * (hit - pos["entry"]) / abs(pos["entry"] - pos["stop"])})
                pos = None
            continue
        if mins < 570 + s.no_trade_open_min or mins >= close_min - s.no_new_entries_before_close_min:
            continue
        sig = evaluate(symbol, bars.iloc[max(0, i - window): i + 1], s)
        if sig is None or (sig.side == "short" and not s.allow_shorts):
            continue
        entry = float(bars.iloc[i + 1]["open"])
        shift = entry - sig.entry
        stop, target = sig.stop + shift, sig.target + shift
        qty = position_size(equity, entry, stop, s)
        if qty < 1:
            continue
        pos = {"time": ny[i + 1], "side": sig.side, "qty": qty, "entry": entry, "stop": stop,
               "target": target, "reasons": "; ".join(sig.reasons)}
    return trades, equity


def report(trades, start_equity, end_equity):
    if not trades:
        print("No trades.")
        return
    df = pd.DataFrame(trades)
    wins, losses = df[df.pnl > 0], df[df.pnl <= 0]
    curve = start_equity + df.pnl.cumsum()
    max_dd = ((curve.cummax() - curve) / curve.cummax()).max()
    pf = wins.pnl.sum() / abs(losses.pnl.sum()) if len(losses) and losses.pnl.sum() != 0 else float("inf")
    print(f"Trades: {len(df)}  (long {sum(df.side == 'long')}, short {sum(df.side == 'short')})")
    print(f"Win rate: {len(wins) / len(df):.1%}")
    print(f"Avg R: {df.r.mean():.2f}")
    print(f"Profit factor: {pf:.2f}")
    print(f"Total P&L: ${end_equity - start_equity:,.2f} ({(end_equity / start_equity - 1):.2%})")
    print(f"Max drawdown: {max_dd:.2%}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("symbol")
    p.add_argument("--days", type=int, default=20)
    a = p.parse_args()
    s = V2Settings()
    from v2.broker import Broker
    b = Broker(s)
    end = datetime.now(timezone.utc) - timedelta(minutes=20)
    bars = b.bars(a.symbol.upper(), days=a.days, end=end)
    print(f"Loaded {len(bars)} bars for {a.symbol.upper()}. Running backtest (can take a minute)...")
    trades, final = simulate(a.symbol.upper(), bars, s)
    report(trades, 100000.0, final)
    os.makedirs("logs", exist_ok=True)
    if trades:
        out = f"logs/backtest_{a.symbol.upper()}.csv"
        pd.DataFrame(trades).to_csv(out, index=False)
        print(f"Trade list saved to {out}")


if __name__ == "__main__":
    main()
