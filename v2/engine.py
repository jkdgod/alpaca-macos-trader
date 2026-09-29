import logging
import time
from datetime import timedelta

from .indicators import NY
from .journal import Journal
from .risk import DailyRisk, position_size
from .strategy import evaluate

log = logging.getLogger("v2.engine")


class EngineV2:
    def __init__(self, settings, broker):
        self.s = settings
        self.b = broker
        self.risk = DailyRisk(settings.daily_loss_limit_pct)
        self.journal = Journal(settings.journal_path)
        self.flattened_date = None
        self.session_seen = False
        self.cooldown = {}

    def run(self):
        log.info("V2 engine started paper=%s watchlist=%s shorts=%s", self.s.is_paper,
                 ",".join(self.s.watchlist), self.s.allow_shorts)
        while True:
            try:
                if not self.step():
                    break
            except Exception:
                log.exception("Loop error")
            time.sleep(self.s.poll_seconds)
        log.info("V2 engine stopped")

    def step(self):
        clock = self.b.clock()
        now = clock.timestamp.astimezone(NY)

        if not clock.is_open:
            if self.session_seen:
                log.info("Market closed for the day, exiting")
                return False
            wait_h = (clock.next_open - clock.timestamp).total_seconds() / 3600
            if wait_h > 16:
                log.info("Next open is %.1f hours away (weekend/holiday), exiting", wait_h)
                return False
            return True

        self.session_seen = True
        today = now.date()
        equity = self.b.equity()
        frozen = self.risk.update(today, equity)
        mins_to_close = (clock.next_close - clock.timestamp).total_seconds() / 60
        mins_since_open = (now - now.replace(hour=9, minute=30, second=0, microsecond=0)).total_seconds() / 60

        if mins_to_close <= self.s.flatten_before_close_min:
            if self.flattened_date != today:
                self.b.flatten()
                self.flattened_date = today
                self.journal.day_summary(now, self.risk.start_equity, self.b.equity())
                log.info("End of day. start=%.2f end=%.2f", self.risk.start_equity or 0, equity)
            return True

        if frozen:
            if self.flattened_date != today:
                log.error("Daily loss limit hit (%.2f%%). Flattening and stopping new trades today.",
                          self.risk.drawdown_pct(equity) * 100)
                self.b.flatten()
                self.flattened_date = today
            return True

        if mins_since_open < self.s.no_trade_open_min or mins_to_close <= self.s.no_new_entries_before_close_min:
            return True

        busy = set(self.b.positions()) | self.b.open_order_symbols()
        for sym in self.s.watchlist:
            if len(busy) >= self.s.max_positions:
                break
            if sym in busy:
                continue
            last = self.cooldown.get(sym)
            if last and now - last < timedelta(minutes=self.s.cooldown_min):
                continue
            try:
                self._consider(sym, equity, now, busy)
            except Exception:
                log.exception("Symbol %s failed", sym)
        return True

    def _consider(self, sym, equity, now, busy):
        bars = self.b.bars(sym)
        if bars.empty:
            log.warning("No bars for %s", sym)
            return
        sig = evaluate(sym, bars, self.s)
        if sig is None:
            return
        if sig.side == "short":
            if not self.s.allow_shorts:
                return
            if not self.b.can_short(sym):
                log.info("%s short signal skipped: not easy-to-borrow today", sym)
                return
        qty = position_size(equity, sig.entry, sig.stop, self.s)
        if qty < 1:
            return
        order = self.b.submit_bracket(sym, qty, sig.side, sig.stop, sig.target)
        log.info("ENTRY %s %s qty=%d entry~%.2f stop=%.2f target=%.2f score=%d reasons=%s",
                 sig.side.upper(), sym, qty, sig.entry, sig.stop, sig.target, sig.score, "; ".join(sig.reasons))
        self.journal.entry(now, sig, qty, str(getattr(order, "id", "")))
        busy.add(sym)
        self.cooldown[sym] = now
