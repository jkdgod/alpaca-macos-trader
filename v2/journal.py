import csv
import os

FIELDS = ["time", "type", "symbol", "side", "qty", "entry", "stop", "target", "score", "reasons",
          "order_id", "start_equity", "end_equity", "pnl"]


class Journal:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _write(self, row):
        new = not os.path.exists(self.path)
        with open(self.path, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in FIELDS})

    def entry(self, when, sig, qty, order_id):
        self._write({"time": when.isoformat(), "type": "entry", "symbol": sig.symbol, "side": sig.side,
                     "qty": qty, "entry": round(sig.entry, 2), "stop": round(sig.stop, 2),
                     "target": round(sig.target, 2), "score": sig.score, "reasons": "; ".join(sig.reasons),
                     "order_id": order_id})

    def day_summary(self, when, start_equity, end_equity):
        pnl = (end_equity - start_equity) if start_equity else ""
        self._write({"time": when.isoformat(), "type": "day", "start_equity": start_equity,
                     "end_equity": end_equity, "pnl": round(pnl, 2) if pnl != "" else ""})
