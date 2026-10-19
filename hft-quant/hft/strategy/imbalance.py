"""Order book imbalance momentum: take liquidity when the book leans hard one way,
exit on take-profit, stop-loss, or a holding-time limit."""
from __future__ import annotations

from ..models import Order, OrderBook, Side
from ..portfolio import Position
from .base import Actions, Strategy


class ImbalanceTaker(Strategy):
    name = "imbalance"

    def __init__(self, instrument, order_qty: float = 0.001, threshold: float = 0.6,
                 depth: int = 5, take_profit_ticks: int = 4, stop_loss_ticks: int = 4,
                 max_hold: float = 5.0, **params) -> None:
        super().__init__(instrument, **params)
        self.order_qty = order_qty
        self.threshold = threshold
        self.depth = depth
        self.tp = take_profit_ticks * instrument.tick_size
        self.sl = stop_loss_ticks * instrument.tick_size
        self.max_hold = max_hold
        self._entry_ts: float | None = None

    def on_book(self, book: OrderBook, position: Position, open_orders: list[Order]) -> Actions:
        acts = Actions()
        if open_orders:
            return acts
        if position.qty != 0:
            if self._entry_ts is None:
                self._entry_ts = book.ts
            move = (book.mid - position.avg_price) * (1 if position.qty > 0 else -1)
            if move >= self.tp or move <= -self.sl or book.ts - self._entry_ts >= self.max_hold:
                side = Side.SELL if position.qty > 0 else Side.BUY
                acts.place.append(Order(self.inst.symbol, side, abs(position.qty),
                                        reduce_only=True, tag=self.name))
            return acts
        self._entry_ts = None
        imb = book.imbalance(self.depth)
        if abs(imb) >= self.threshold:
            side = Side.BUY if imb > 0 else Side.SELL
            acts.place.append(Order(self.inst.symbol, side, self.order_qty, tag=self.name))
        return acts
