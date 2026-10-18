"""Simulated exchange that matches orders against the incoming order book.

Fill model (deliberately simple, and optimistic for makers):
- Market orders and marketable limit orders fill immediately at the touch as taker.
- Resting limit orders fill as maker once the opposite touch trades through their price.
- Queue position and partial depth are ignored; `latency` delays when an order becomes live.
"""
from __future__ import annotations

from ..models import Fill, Instrument, Order, OrderBook, OrderStatus, Side
from .base import Exchange


class PaperExchange(Exchange):
    def __init__(self, instruments: dict[str, Instrument], latency: float = 0.0) -> None:
        super().__init__()
        self.instruments = instruments
        self.latency = latency
        self.books: dict[str, OrderBook] = {}
        self._orders: dict[str, Order] = {}
        self._now = 0.0

    async def place(self, order: Order) -> Order:
        book = self.books.get(order.symbol)
        if book is None:
            order.status = OrderStatus.REJECTED
            return order
        order.ts = self._now + self.latency
        crosses = order.is_market or (
            order.price >= book.best_ask if order.side is Side.BUY else order.price <= book.best_bid
        )
        if crosses and order.post_only:
            order.status = OrderStatus.REJECTED
            return order
        self._orders[order.id] = order
        if crosses and self.latency == 0:
            self._fill(order, book.best_ask if order.side is Side.BUY else book.best_bid, maker=False)
        return order

    async def cancel(self, order_id: str) -> None:
        o = self._orders.pop(order_id, None)
        if o and o.status is OrderStatus.OPEN:
            o.status = OrderStatus.CANCELED

    def open_orders(self, symbol: str | None = None) -> list[Order]:
        return [o for o in self._orders.values() if symbol is None or o.symbol == symbol]

    def on_book(self, book: OrderBook) -> None:
        self.books[book.symbol] = book
        self._now = book.ts
        for o in list(self._orders.values()):
            if o.symbol != book.symbol or o.ts > book.ts:
                continue
            if o.is_market:
                self._fill(o, book.best_ask if o.side is Side.BUY else book.best_bid, maker=False)
            elif o.side is Side.BUY and book.best_ask <= o.price:
                self._fill(o, o.price, maker=True)
            elif o.side is Side.SELL and book.best_bid >= o.price:
                self._fill(o, o.price, maker=True)

    def _fill(self, order: Order, price: float, maker: bool) -> None:
        inst = self.instruments[order.symbol]
        qty = order.remaining
        fee = qty * price * (inst.maker_fee if maker else inst.taker_fee)
        order.filled = order.qty
        order.status = OrderStatus.FILLED
        self._orders.pop(order.id, None)
        self._emit_fill(Fill(order.id, order.symbol, order.side, qty, price, fee, self._now, maker))
