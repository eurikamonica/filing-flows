"""Pre-trade risk checks and a kill switch. Every order passes through here."""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from .models import Order, Side
from .portfolio import Portfolio

log = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    max_position_notional: float = 1_000.0  # per instrument, quote currency
    max_gross_notional: float = 3_000.0
    max_order_notional: float = 200.0
    max_orders_per_sec: int = 20
    max_drawdown: float = 100.0  # stop trading once PnL falls this far below its peak
    max_price_deviation: float = 0.01  # limit price must sit within 1% of mid


class RiskManager:
    def __init__(self, limits: RiskLimits, portfolio: Portfolio) -> None:
        self.limits = limits
        self.portfolio = portfolio
        self.killed = False
        self.kill_reason = ""
        self._peak_pnl = 0.0
        self._order_times: deque[float] = deque()

    def kill(self, reason: str) -> None:
        if not self.killed:
            log.error("KILL SWITCH: %s", reason)
            self.killed, self.kill_reason = True, reason

    def on_mark(self, marks: dict[str, float]) -> None:
        pnl = self.portfolio.equity_pnl(marks)
        self._peak_pnl = max(self._peak_pnl, pnl)
        if self._peak_pnl - pnl > self.limits.max_drawdown:
            self.kill(f"drawdown {self._peak_pnl - pnl:.2f} > {self.limits.max_drawdown}")

    def check(self, order: Order, mid: float, marks: dict[str, float], now: float | None = None) -> str | None:
        """Return None if the order is allowed, otherwise the reason for rejection."""
        if self.killed:
            return f"killed: {self.kill_reason}"
        now = time.time() if now is None else now
        while self._order_times and now - self._order_times[0] > 1.0:
            self._order_times.popleft()
        if len(self._order_times) >= self.limits.max_orders_per_sec:
            return "order rate limit"

        px = order.price if order.price is not None else mid
        if order.price is not None and abs(order.price - mid) / mid > self.limits.max_price_deviation:
            return "price too far from mid"
        if order.qty * px > self.limits.max_order_notional:
            return "order notional too large"

        if not order.reduce_only:
            pos = self.portfolio.pos(order.symbol)
            new_qty = pos.qty + order.qty * order.side.sign
            if abs(new_qty) > abs(pos.qty) and abs(new_qty) * mid > self.limits.max_position_notional:
                return "position limit"
            gross = self.portfolio.gross_notional(marks) - pos.notional(mid) + abs(new_qty) * mid
            if abs(new_qty) > abs(pos.qty) and gross > self.limits.max_gross_notional:
                return "gross notional limit"
        else:
            held = self.portfolio.pos(order.symbol).qty
            if (order.side is Side.BUY and held >= 0) or (order.side is Side.SELL and held <= 0):
                return "reduce-only order would increase position"

        self._order_times.append(now)
        return None
