import logging
from datetime import datetime, timedelta, timezone

import pandas as pd
from alpaca.data.enums import DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest, StopLossRequest, TakeProfitRequest

log = logging.getLogger("v2.broker")


class Broker:
    def __init__(self, settings):
        self.trading = TradingClient(settings.api_key, settings.secret_key, paper=settings.is_paper)
        self.data = StockHistoricalDataClient(settings.api_key, settings.secret_key)
        self.feed = DataFeed(settings.data_feed)

    def clock(self):
        return self.trading.get_clock()

    def account(self):
        return self.trading.get_account()

    def equity(self):
        return float(self.account().equity)

    def positions(self):
        return {p.symbol: p for p in self.trading.get_all_positions()}

    def open_order_symbols(self):
        orders = self.trading.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True))
        return {o.symbol for o in orders}

    def can_short(self, symbol):
        asset = self.trading.get_asset(symbol)
        return bool(asset.shortable and asset.easy_to_borrow)

    def bars(self, symbol, days=5, end=None):
        end = end or datetime.now(timezone.utc)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Minute,
                               start=end - timedelta(days=days), end=end, feed=self.feed)
        df = self.data.get_stock_bars(req).df
        if df.empty:
            return df
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level=0)
        return df[["open", "high", "low", "close", "volume"]].sort_index()

    def submit_bracket(self, symbol, qty, side, stop, target):
        req = MarketOrderRequest(
            symbol=symbol,
            qty=int(qty),
            side=OrderSide.BUY if side == "long" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(target, 2)),
            stop_loss=StopLossRequest(stop_price=round(stop, 2)),
        )
        return self.trading.submit_order(req)

    def flatten(self):
        self.trading.cancel_orders()
        self.trading.close_all_positions(cancel_orders=True)
        log.warning("Flattened: all orders cancelled, all positions closed")
