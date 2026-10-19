"""Strategy interface. Strategies return desired actions; the engine routes them via risk."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Fill, Instrument, Order, OrderBook
from ..portfolio import Position


@dataclass
class Actions:
    place: list[Order] = field(default_factory=list)
    cancel: list[str] = field(default_factory=list)


class Strategy:
    name = "base"

    def __init__(self, instrument: Instrument, **params) -> None:
        self.inst = instrument
        self.params = params

    def on_book(self, book: OrderBook, position: Position, open_orders: list[Order]) -> Actions:
        return Actions()

    def on_fill(self, fill: Fill) -> None:
        pass
