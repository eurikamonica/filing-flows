"""Event loop: book -> exchange matching -> risk marks -> strategy -> risk check -> exchange."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from .exchange.base import Exchange
from .models import Fill, Order, OrderBook, OrderStatus, Side
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy.base import Strategy

log = logging.getLogger(__name__)


@dataclass
class Stats:
    books: int = 0
    orders: int = 0
    fills: int = 0
    maker_fills: int = 0
    rejects: dict[str, int] = field(default_factory=dict)
    pnl_curve: list[tuple[float, float]] = field(default_factory=list)
    volume: float = 0.0


class Engine:
    def __init__(self, exchange: Exchange, strategies: dict[str, Strategy],
                 risk: RiskManager, portfolio: Portfolio, sample_every: int = 50) -> None:
        self.exchange = exchange
        self.strategies = strategies
        self.risk = risk
        self.portfolio = portfolio
        self.marks: dict[str, float] = {}
        self.stats = Stats()
        self.sample_every = sample_every
        self._flattened = False
        exchange.on_fill(self._on_fill)

    def _on_fill(self, fill: Fill) -> None:
        self.portfolio.on_fill(fill)
        self.stats.fills += 1
        self.stats.maker_fills += fill.maker
        self.stats.volume += fill.qty * fill.price
        strat = self.strategies.get(fill.symbol)
        if strat:
            strat.on_fill(fill)
        log.debug("fill %s %s %.6f @ %.4f maker=%s", fill.symbol, fill.side.value, fill.qty, fill.price, fill.maker)

    async def _submit(self, order: Order, mid: float) -> None:
        reason = self.risk.check(order, mid, self.marks, now=self._now)
        if reason:
            self.stats.rejects[reason] = self.stats.rejects.get(reason, 0) + 1
            return
        self.stats.orders += 1
        placed = await self.exchange.place(order)
        if placed.status is OrderStatus.REJECTED:
            self.stats.rejects["exchange"] = self.stats.rejects.get("exchange", 0) + 1

    async def flatten_all(self) -> None:
        """Cancel everything and close positions with reduce-only market orders."""
        for o in list(self.exchange.open_orders()):
            await self.exchange.cancel(o.id)
        for sym, p in self.portfolio.positions.items():
            if abs(p.qty) > 1e-12:
                side = Side.SELL if p.qty > 0 else Side.BUY
                await self.exchange.place(Order(sym, side, abs(p.qty), reduce_only=True, tag="flatten"))

    async def on_book(self, book: OrderBook) -> None:
        self._now = book.ts
        self.stats.books += 1
        self.exchange.on_book(book)
        self.marks[book.symbol] = book.mid
        self.risk.on_mark(self.marks)
        if self.stats.books % self.sample_every == 0:
            self.stats.pnl_curve.append((book.ts, self.portfolio.equity_pnl(self.marks)))

        if self.risk.killed:
            if not self._flattened:
                self._flattened = True
                await self.flatten_all()
            return

        strat = self.strategies.get(book.symbol)
        if strat is None:
            return
        acts = strat.on_book(book, self.portfolio.pos(book.symbol), self.exchange.open_orders(book.symbol))
        for oid in acts.cancel:
            await self.exchange.cancel(oid)
        for order in acts.place:
            await self._submit(order, book.mid)

    async def run(self, feed: AsyncIterator[OrderBook], max_books: int | None = None) -> Stats:
        self._now = 0.0
        try:
            async for book in feed:
                await self.on_book(book)
                if max_books and self.stats.books >= max_books:
                    break
        finally:
            await self.flatten_all()
        return self.stats
