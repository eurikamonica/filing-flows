"""Position and PnL accounting per instrument."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Fill


@dataclass
class Position:
    symbol: str
    qty: float = 0.0
    avg_price: float = 0.0
    realized: float = 0.0
    fees: float = 0.0

    def apply(self, fill: Fill) -> None:
        signed = fill.qty * fill.side.sign
        self.fees += fill.fee
        if self.qty == 0 or (self.qty > 0) == (signed > 0):
            new_qty = self.qty + signed
            self.avg_price = (self.avg_price * abs(self.qty) + fill.price * abs(signed)) / abs(new_qty)
            self.qty = new_qty
            return
        closing = min(abs(signed), abs(self.qty))
        direction = 1 if self.qty > 0 else -1
        self.realized += closing * (fill.price - self.avg_price) * direction
        new_qty = self.qty + signed
        if abs(new_qty) < 1e-12:
            self.qty, self.avg_price = 0.0, 0.0
        elif (new_qty > 0) != (self.qty > 0):
            self.qty, self.avg_price = new_qty, fill.price  # flipped side
        else:
            self.qty = new_qty

    def unrealized(self, mark: float) -> float:
        return self.qty * (mark - self.avg_price)

    def notional(self, mark: float) -> float:
        return abs(self.qty) * mark


class Portfolio:
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def pos(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position(symbol))

    def on_fill(self, fill: Fill) -> None:
        self.pos(fill.symbol).apply(fill)

    def equity_pnl(self, marks: dict[str, float]) -> float:
        """Realized + unrealized - fees across all instruments."""
        total = 0.0
        for sym, p in self.positions.items():
            total += p.realized - p.fees + p.unrealized(marks.get(sym, p.avg_price))
        return total

    def gross_notional(self, marks: dict[str, float]) -> float:
        return sum(p.notional(marks.get(s, p.avg_price)) for s, p in self.positions.items())
