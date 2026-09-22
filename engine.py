from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
from collections import deque
from datetime import datetime
from threading import Thread
from typing import Deque
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest

from config.settings import Settings
from execution.broker import AlpacaBroker, PositionSnapshot
from risk.risk_manager import RiskManager
from scheduling.scheduler import MarketScheduler, SessionState
from strategy.strategy import EmaVolumeCrossStrategy, SignalAction, StrategySignal

logger = logging.getLogger(__name__)
EASTERN = ZoneInfo("America/New_York")


class TradingEngine:
    def __init__(self, settings: Settings, broker: AlpacaBroker, risk_manager: RiskManager, scheduler: MarketScheduler, strategy: EmaVolumeCrossStrategy) -> None:
        self.settings = settings
        self.broker = broker
        self.risk_manager = risk_manager
        self.scheduler = scheduler
        self.strategy = strategy
        self.running = True
        self.market_active = False
        self.pre_close_done = False
        self.stream: StockDataStream | None = None
        self.stream_thread: Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.dispatch_lock = asyncio.Lock()
        self.buffer_size = max(settings.warmup_bars, settings.min_bars_required) + 10
        self.bars: dict[str, Deque[dict]] = {symbol: deque(maxlen=self.buffer_size) for symbol in settings.watchlist}
        self.last_bar_timestamp: dict[str, str] = {}
        self.dispatched_signal_ids: set[str] = set()

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._install_signal_handlers()
        logger.info("Engine started mode=%s watchlist=%s", self.settings.trading_mode, ",".join(self.settings.watchlist))
        while self.running:
            try:
                state, session = await asyncio.to_thread(self.scheduler.state_at)
                if state == SessionState.CLOSED:
                    self.market_active = False
                    await self._stop_stream()
                    self.pre_close_done = False
                    await self.scheduler.sleep_until_next_pre_market()
                    continue
                if state == SessionState.PRE_MARKET and session:
                    await self._prepare_session(session.trading_date)
                    await self._sleep_until(session.open_at)
                    continue
                if state == SessionState.MARKET_OPEN and session:
                    await self._activate_market(session.trading_date)
                    await asyncio.sleep(5)
                    continue
                if state == SessionState.PRE_CLOSE_FLUSH:
                    await self._pre_close_flush()
                    if session:
                        await self._sleep_until(session.close_at)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Engine loop error: %s", exc)
                await asyncio.sleep(15)
        await self._shutdown()

    async def _prepare_session(self, trading_date) -> None:
        account = await asyncio.to_thread(self.broker.verify_connectivity)
        await asyncio.to_thread(self.risk_manager.begin_session, trading_date, account)
        await self._warmup_bars()
        self.pre_close_done = False

    async def _activate_market(self, trading_date) -> None:
        account = await asyncio.to_thread(self.broker.get_account_snapshot)
        await asyncio.to_thread(self.risk_manager.begin_session, trading_date, account)
        if await asyncio.to_thread(self.risk_manager.enforce_daily_drawdown, account):
            self.market_active = False
            return
        if not self.market_active:
            await self._warmup_bars()
            self.market_active = True
            await self._start_stream()

    async def _warmup_bars(self) -> None:
        historical = await asyncio.to_thread(self.broker.get_minute_bars, self.settings.watchlist, self.settings.warmup_bars)
        for symbol, frame in historical.items():
            if frame.empty:
                logger.warning("No warmup bars returned for %s", symbol)
                continue
            rows = [{"timestamp": pd.Timestamp(timestamp).isoformat(), "open": float(row["open"]), "high": float(row["high"]), "low": float(row["low"]), "close": float(row["close"]), "volume": float(row["volume"])} for timestamp, row in frame.iterrows()]
            self.bars[symbol].clear()
            self.bars[symbol].extend(rows[-self.buffer_size:])
            self.last_bar_timestamp[symbol] = rows[-1]["timestamp"]
            logger.info("Warmup complete symbol=%s bars=%d", symbol, len(rows))

    async def _start_stream(self) -> None:
        if self.stream is not None:
            return
        feed = DataFeed.IEX if self.settings.data_feed == "iex" else DataFeed.SIP
        self.stream = StockDataStream(self.settings.api_key_id, self.settings.api_secret_key, feed=feed)
        self.stream.subscribe_bars(self._on_stream_bar, *self.settings.watchlist)
        self.stream_thread = Thread(target=self.stream.run, name="alpaca-minute-bars", daemon=True)
        self.stream_thread.start()
        logger.info("Market-data stream started")

    def _on_stream_bar(self, bar) -> None:
        if self.loop is None or not self.running:
            return
        future = asyncio.run_coroutine_threadsafe(self._handle_bar(bar), self.loop)
        future.add_done_callback(self._log_stream_callback_error)

    @staticmethod
    def _log_stream_callback_error(future) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.exception("Bar handler failed: %s", exc)

    async def _handle_bar(self, bar) -> None:
        if not self.market_active:
            return
        symbol = str(bar.symbol).upper()
        if symbol not in self.bars:
            return
        timestamp = bar.timestamp.astimezone(EASTERN).isoformat()
        if self.last_bar_timestamp.get(symbol) == timestamp:
            return
        self.last_bar_timestamp[symbol] = timestamp
        self.bars[symbol].append({"timestamp": timestamp, "open": float(bar.open), "high": float(bar.high), "low": float(bar.low), "close": float(bar.close), "volume": float(bar.volume)})
        frame = pd.DataFrame(self.bars[symbol])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp")
        position = await asyncio.to_thread(self.broker.get_position, symbol)
        signal_value = self.strategy.evaluate(symbol, frame, position is not None)
        if signal_value.action != SignalAction.HOLD:
            await self._dispatch(signal_value, position)

    async def _dispatch(self, signal_value: StrategySignal, position: PositionSnapshot | None) -> None:
        async with self.dispatch_lock:
            if not self.market_active:
                return
            state, _ = await asyncio.to_thread(self.scheduler.state_at)
            if state != SessionState.MARKET_OPEN:
                return
            account = await asyncio.to_thread(self.broker.get_account_snapshot)
            if await asyncio.to_thread(self.risk_manager.enforce_daily_drawdown, account):
                self.market_active = False
                return
            signal_id = self._signal_id(signal_value)
            if signal_id in self.dispatched_signal_ids:
                return
            client_order_id = self._client_order_id(signal_value, signal_id)
            if await self._order_exists(client_order_id):
                self.dispatched_signal_ids.add(signal_id)
                return
            if signal_value.action == SignalAction.ENTER_LONG:
                approval = await asyncio.to_thread(self.risk_manager.validate_entry, signal_value.symbol, signal_value.price)
                if not approval.approved:
                    logger.info("Entry denied symbol=%s reason=%s", signal_value.symbol, approval.reason)
                    return
                request = MarketOrderRequest(symbol=signal_value.symbol, qty=approval.qty, side=OrderSide.BUY, time_in_force=TimeInForce.DAY, order_class=OrderClass.BRACKET, take_profit=TakeProfitRequest(limit_price=approval.take_profit_price), stop_loss=StopLossRequest(stop_price=approval.stop_price), client_order_id=client_order_id)
                order = await asyncio.to_thread(self.broker.client.submit_order, order_data=request)
                self.dispatched_signal_ids.add(signal_id)
                logger.warning("Entry submitted symbol=%s qty=%d order_id=%s", signal_value.symbol, approval.qty, order.id)
                return
            if signal_value.action == SignalAction.EXIT_LONG:
                current = position or await asyncio.to_thread(self.broker.get_position, signal_value.symbol)
                if current is None or current.qty <= 0:
                    return
                await asyncio.to_thread(self.broker.cancel_open_orders_for_symbol, signal_value.symbol)
                order = await asyncio.to_thread(self.broker.submit_exit_market_order, signal_value.symbol, current.qty, client_order_id)
                self.dispatched_signal_ids.add(signal_id)
                logger.warning("Exit submitted symbol=%s qty=%.6f order_id=%s", signal_value.symbol, current.qty, order.id)

    async def _order_exists(self, client_order_id: str) -> bool:
        try:
            await asyncio.to_thread(self.broker.get_order_by_client_id, client_order_id)
            return True
        except Exception:
            return False

    @staticmethod
    def _signal_id(signal_value: StrategySignal) -> str:
        raw = f"{signal_value.symbol}|{signal_value.action}|{signal_value.bar_timestamp}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    @staticmethod
    def _client_order_id(signal_value: StrategySignal, signal_id: str) -> str:
        action = "entry" if signal_value.action == SignalAction.ENTER_LONG else "exit"
        return f"ema921-{action}-{signal_value.symbol.lower()}-{signal_id}"

    async def _pre_close_flush(self) -> None:
        if self.pre_close_done:
            return
        self.pre_close_done = True
        self.market_active = False
        await self._stop_stream()
        await asyncio.to_thread(self.broker.cancel_all_open_orders)
        if self.settings.close_intraday_positions:
            positions = await asyncio.to_thread(self.broker.get_positions)
            symbols = [position.symbol for position in positions if position.symbol in self.settings.watchlist]
            await asyncio.to_thread(self.broker.close_positions, symbols)
        logger.warning("Pre-close flush complete")

    async def _stop_stream(self) -> None:
        if self.stream is None:
            return
        try:
            await self.stream.stop_ws()
        except Exception as exc:
            logger.warning("Stream stop warning: %s", exc)
        self.stream = None
        self.stream_thread = None

    async def _sleep_until(self, target: datetime) -> None:
        while self.running:
            seconds = (target - datetime.now(EASTERN)).total_seconds()
            if seconds <= 0:
                return
            await asyncio.sleep(min(seconds, 60))

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        def shutdown() -> None:
            self.running = False
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, shutdown)
            except NotImplementedError:
                signal.signal(sig, lambda *_: shutdown())

    async def _shutdown(self) -> None:
        self.market_active = False
        await self._stop_stream()
        logger.info("Engine stopped")
