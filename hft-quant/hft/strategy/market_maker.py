"""Inventory-aware market maker in the spirit of Avellaneda-Stoikov.

Quotes around a reservation price that is skewed against current inventory,
with an order-book-imbalance tilt. Requotes only when the target moves by at
least `requote_ticks`, to limit message rate.
"""
from __future__ import annotations

from collections import deque
import math

from ..models import Order, OrderBook, Side
from ..portfolio import Position
from .base import Actions, Strategy


class MarketMaker(Strategy):
    name = "market_maker"

    def __init__(self, instrument, order_qty: float = 0.001, gamma: float = 0.1,
                 min_spread_ticks: int = 2, max_inventory: float = 0.01,
                 imbalance_weight: float = 0.5, requote_ticks: int = 1,
                 vol_window: int = 100, **params) -> None:
        super().__init__(instrument, **params)
        self.order_qty = order_qty
        self.gamma = gamma
        self.min_spread_ticks = min_spread_ticks
        self.max_inventory = max_inventory
        self.imbalance_weight = imbalance_weight
        self.requote_ticks = requote_ticks
        self._mids: deque[float] = deque(maxlen=vol_window)

    def _vol(self) -> float:
        """Std dev of mid changes over the window, in price units."""
        if len(self._mids) < 3:
            return self.inst.tick_size
        m = list(self._mids)
        d = [b - a for a, b in zip(m, m[1:])]
        mean = sum(d) / len(d)
        return max(math.sqrt(sum((x - mean) ** 2 for x in d) / len(d)), self.inst.tick_size)

    def on_book(self, book: OrderBook, position: Position, open_orders: list[Order]) -> Actions:
        tick = self.inst.tick_size
        self._mids.append(book.mid)
        sigma = self._vol()
        inv = position.qty / self.max_inventory  # normalised to [-1, 1] at the limit

        reservation = book.mid - inv * self.gamma * sigma * 10 \
            + self.imbalance_weight * book.imbalance() * book.spread / 2
        half = max(self.min_spread_ticks * tick / 2, self.gamma * sigma)
        bid = self.inst.round_price(min(reservation - half, book.best_ask - tick))
        ask = self.inst.round_price(max(reservation + half, book.best_bid + tick))

        targets: dict[Side, float | None] = {
            Side.BUY: bid if position.qty < self.max_inventory else None,
            Side.SELL: ask if position.qty > -self.max_inventory else None,
        }
        acts = Actions()
        for side, px in targets.items():
            live = [o for o in open_orders if o.side is side]
            keep = [o for o in live if px is not None and abs(o.price - px) < self.requote_ticks * tick]
            acts.cancel += [o.id for o in live if o not in keep]
            if px is not None and not keep:
                acts.place.append(Order(self.inst.symbol, side, self.order_qty, px,
                                        post_only=True, tag=self.name))
        return acts
