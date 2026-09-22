from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from config.settings import Settings
from execution.broker import AccountSnapshot, AlpacaBroker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradeApproval:
    approved: bool
    reason: str
    qty: int = 0
    notional: float = 0.0
    stop_price: float = 0.0
    take_profit_price: float = 0.0


class RiskManager:
    def __init__(self, settings: Settings, broker: AlpacaBroker) -> None:
        self.settings = settings
        self.broker = broker
        self.state_path: Path = settings.state_directory / "risk_state.json"
        self.session_date: str | None = None
        self.session_start_equity = 0.0
        self.execution_frozen = False
        self.freeze_reason = ""
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.session_date = state.get("session_date")
            self.session_start_equity = float(state.get("session_start_equity", 0.0))
            self.execution_frozen = bool(state.get("execution_frozen", False))
            self.freeze_reason = str(state.get("freeze_reason", ""))
        except Exception as exc:
            logger.warning("Unable to load risk state; using safe defaults: %s", exc)

    def _save_state(self) -> None:
        payload = {
            "session_date": self.session_date,
            "session_start_equity": self.session_start_equity,
            "execution_frozen": self.execution_frozen,
            "freeze_reason": self.freeze_reason,
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def begin_session(self, trading_date: date, account: AccountSnapshot) -> None:
        date_key = trading_date.isoformat()
        if self.session_date != date_key:
            self.session_date = date_key
            self.session_start_equity = account.equity
            self.execution_frozen = False
            self.freeze_reason = ""
            self._save_state()
            logger.info(
                "Session risk baseline equity=%.2f date=%s",
                account.equity,
                self.session_date,
            )

    def daily_drawdown_pct(self, account: AccountSnapshot) -> float:
        if self.session_start_equity <= 0:
            return 0.0
        return max(
            0.0,
            (self.session_start_equity - account.equity)
            / self.session_start_equity,
        )

    def enforce_daily_drawdown(self, account: AccountSnapshot) -> bool:
        if self.execution_frozen:
            return True
        drawdown = self.daily_drawdown_pct(account)
        if drawdown >= self.settings.max_daily_drawdown_pct:
            self.trigger_circuit_breaker(
                f"Daily drawdown {drawdown:.2%} reached threshold "
                f"{self.settings.max_daily_drawdown_pct:.2%}."
            )
            return True
        return False

    def validate_entry(self, symbol: str, price: float) -> TradeApproval:
        if not math.isfinite(price) or price <= 0:
            return TradeApproval(False, "Invalid market price.")
        if self.execution_frozen:
            return TradeApproval(False, f"Execution frozen: {self.freeze_reason}")

        account = self.broker.get_account_snapshot()
        if self.enforce_daily_drawdown(account):
            return TradeApproval(False, f"Execution frozen: {self.freeze_reason}")

        positions = self.broker.get_positions()
        if any(position.symbol == symbol for position in positions):
            return TradeApproval(False, f"Position already exists for {symbol}.")
        if any(
            order.symbol == symbol and str(order.side).lower().endswith("buy")
            for order in self.broker.get_open_orders()
        ):
            return TradeApproval(False, f"Open buy order already exists for {symbol}.")
        if len(positions) >= self.settings.max_positions:
            return TradeApproval(False, "Maximum position count reached.")

        gross_exposure = sum(abs(position.market_value) for position in positions)
        maximum_gross = account.equity * self.settings.max_gross_leverage
        capacity = max(0.0, maximum_gross - gross_exposure)
        target_notional = min(
            account.equity * self.settings.max_allocation_pct,
            self.settings.max_trade_dollars,
            account.buying_power,
            capacity,
        )
        qty = math.floor(target_notional / price)
        if qty < 1:
            return TradeApproval(False, "No whole-share quantity fits within risk limits.")

        notional = qty * price
        projected_leverage = (
            (gross_exposure + notional) / account.equity
            if account.equity
            else float("inf")
        )
        if projected_leverage > self.settings.max_gross_leverage:
            return TradeApproval(False, "Projected leverage exceeds cap.")

        return TradeApproval(
            approved=True,
            reason="Approved",
            qty=qty,
            notional=notional,
            stop_price=round(price * (1 - self.settings.stop_loss_pct), 2),
            take_profit_price=round(
                price * (1 + self.settings.take_profit_pct),
                2,
            ),
        )

    def trigger_circuit_breaker(self, reason: str) -> None:
        self.execution_frozen = True
        self.freeze_reason = reason
        self._save_state()
        logger.critical("Circuit breaker activated: %s", reason)
        try:
            self.broker.cancel_all_open_orders()
        finally:
            self.broker.close_all_positions()

    def emergency_kill_switch(
        self,
        reason: str = "Manual kill switch activated.",
    ) -> None:
        self.trigger_circuit_breaker(reason)

    def status(self, account: AccountSnapshot) -> dict:
        return {
            "session_date": self.session_date,
            "session_start_equity": self.session_start_equity,
            "current_equity": account.equity,
            "daily_drawdown_pct": self.daily_drawdown_pct(account),
            "execution_frozen": self.execution_frozen,
            "freeze_reason": self.freeze_reason,
        }
