from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from execution.broker import AlpacaBroker

EASTERN = ZoneInfo("America/New_York")


class SessionState(StrEnum):
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"
    MARKET_OPEN = "MARKET_OPEN"
    PRE_CLOSE_FLUSH = "PRE_CLOSE_FLUSH"


@dataclass(frozen=True)
class MarketSession:
    trading_date: date
    pre_market_at: datetime
    open_at: datetime
    pre_close_at: datetime
    close_at: datetime


class MarketScheduler:
    def __init__(self, broker: AlpacaBroker) -> None:
        self.broker = broker

    def get_session(self, target_date: date) -> MarketSession | None:
        calendar = self.broker.get_trading_calendar(target_date, target_date)
        if not calendar:
            return None

        entry = calendar[0]
        open_at = datetime.combine(entry.date, time.fromisoformat(str(entry.open)), tzinfo=EASTERN)
        close_at = datetime.combine(entry.date, time.fromisoformat(str(entry.close)), tzinfo=EASTERN)
        pre_market_at = open_at - timedelta(minutes=15)
        pre_close_at = min(close_at - timedelta(minutes=5), datetime.combine(entry.date, time(15, 55), tzinfo=EASTERN))
        return MarketSession(entry.date, pre_market_at, open_at, pre_close_at, close_at)

    def state_at(self, moment: datetime | None = None) -> tuple[SessionState, MarketSession | None]:
        now = moment.astimezone(EASTERN) if moment else datetime.now(EASTERN)
        session = self.get_session(now.date())
        if session is None:
            return SessionState.CLOSED, None
        if session.pre_market_at <= now < session.open_at:
            return SessionState.PRE_MARKET, session
        if session.open_at <= now < session.pre_close_at:
            return SessionState.MARKET_OPEN, session
        if session.pre_close_at <= now < session.close_at:
            return SessionState.PRE_CLOSE_FLUSH, session
        return SessionState.CLOSED, session

    async def sleep_until_next_pre_market(self) -> None:
        now = datetime.now(EASTERN)
        for day_offset in range(15):
            candidate_date = (now + timedelta(days=day_offset)).date()
            session = self.get_session(candidate_date)
            if session and session.pre_market_at > now:
                seconds = (session.pre_market_at - now).total_seconds()
                await asyncio.sleep(max(1.0, seconds))
                return
        await asyncio.sleep(3600)
