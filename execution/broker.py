from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetCalendarRequest,
    GetOrdersRequest,
    MarketOrderRequest,
)

from config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    last_equity: float
    buying_power: float
    portfolio_value: float


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    qty: float
    market_value: float
    avg_entry_price: float
    side: str


class AlpacaBroker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = TradingClient(
            settings.api_key_id,
            settings.api_secret_key,
            paper=settings.paper,
            url_override=settings.api_base_url,
        )
        self.data_client = StockHistoricalDataClient(
            settings.api_key_id,
            settings.api_secret_key,
        )

    def verify_connectivity(self) -> AccountSnapshot:
        snapshot = self.get_account_snapshot()
        logger.info(
            "Broker connectivity verified mode=%s equity=%.2f buying_power=%.2f",
            self.settings.trading_mode,
            snapshot.equity,
            snapshot.buying_power,
        )
        return snapshot

    def get_account_snapshot(self) -> AccountSnapshot:
        account = self.client.get_account()
        return AccountSnapshot(
            equity=float(account.equity),
            last_equity=float(account.last_equity),
            buying_power=float(account.buying_power),
            portfolio_value=float(account.portfolio_value),
        )

    def get_positions(self) -> list[PositionSnapshot]:
        return [
            PositionSnapshot(
                symbol=position.symbol,
                qty=float(position.qty),
                market_value=float(position.market_value),
                avg_entry_price=float(position.avg_entry_price),
                side=str(position.side),
            )
            for position in self.client.get_all_positions()
        ]

    def get_position(self, symbol: str) -> PositionSnapshot | None:
        try:
            position = self.client.get_open_position(symbol)
        except Exception:
            return None
        return PositionSnapshot(
            symbol=position.symbol,
            qty=float(position.qty),
            market_value=float(position.market_value),
            avg_entry_price=float(position.avg_entry_price),
            side=str(position.side),
        )

    def get_open_orders(self) -> list:
        request = GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True)
        return list(self.client.get_orders(filter=request))

    def get_order_by_client_id(self, client_order_id: str):
        return self.client.get_order_by_client_id(client_order_id)

    def cancel_all_open_orders(self) -> None:
        results = self.client.cancel_orders()
        logger.warning("Cancel-all requested result_count=%d", len(results))

    def cancel_open_orders_for_symbol(self, symbol: str) -> None:
        for order in self.get_open_orders():
            if order.symbol != symbol:
                continue
            try:
                self.client.cancel_order_by_id(order.id)
            except Exception as exc:
                logger.warning(
                    "Could not cancel order symbol=%s order_id=%s error=%s",
                    symbol,
                    order.id,
                    exc,
                )

    def close_position(self, symbol: str) -> None:
        self.client.close_position(
            symbol_or_asset_id=symbol,
            close_options=ClosePositionRequest(),
        )

    def close_all_positions(self) -> None:
        for position in self.get_positions():
            try:
                self.close_position(position.symbol)
            except Exception as exc:
                logger.exception("Failed to close %s: %s", position.symbol, exc)

    def close_positions(self, symbols: Iterable[str]) -> None:
        for symbol in symbols:
            try:
                self.close_position(symbol)
            except Exception as exc:
                logger.exception("Failed to close %s: %s", symbol, exc)

    def submit_exit_market_order(
        self,
        symbol: str,
        qty: float,
        client_order_id: str,
    ):
        order = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        return self.client.submit_order(order_data=order)

    def get_trading_calendar(self, start: date, end: date):
        request = GetCalendarRequest(start=start, end=end)
        return list(self.client.get_calendar(filters=request))

    def get_minute_bars(
        self,
        symbols: tuple[str, ...],
        limit: int,
    ) -> dict[str, pd.DataFrame]:
        start = datetime.now().astimezone() - timedelta(days=10)
        feed = DataFeed.IEX if self.settings.data_feed == "iex" else DataFeed.SIP
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame.Minute,
            start=start,
            limit=limit,
            feed=feed,
        )
        frame = self.data_client.get_stock_bars(request).df
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if frame.empty:
            return {symbol: empty.copy() for symbol in symbols}

        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            try:
                symbol_frame = frame.xs(symbol, level="symbol").copy()
            except KeyError:
                symbol_frame = empty.copy()
            result[symbol] = symbol_frame[
                ["open", "high", "low", "close", "volume"]
            ].tail(limit)
        return result
