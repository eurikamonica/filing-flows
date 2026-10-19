"""Exchange interface. Strategies and the engine only talk to this abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from ..models import Fill, Order, OrderBook

FillHandler = Callable[[Fill], None]


class Exchange(ABC):
    def __init__(self) -> None:
        self._fill_handlers: list[FillHandler] = []

    def on_fill(self, handler: FillHandler) -> None:
        self._fill_handlers.append(handler)

    def _emit_fill(self, fill: Fill) -> None:
        for h in self._fill_handlers:
            h(fill)

    @abstractmethod
    async def place(self, order: Order) -> Order: ...

    @abstractmethod
    async def cancel(self, order_id: str) -> None: ...

    @abstractmethod
    def open_orders(self, symbol: str | None = None) -> list[Order]: ...

    def on_book(self, book: OrderBook) -> None:
        """Hook for simulated exchanges to match resting orders on each book update."""

    async def close(self) -> None:
        pass
