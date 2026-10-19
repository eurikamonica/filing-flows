"""Core data types shared by feeds, exchanges, strategies and risk."""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    EQUITY = "equity"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


@dataclass(frozen=True)
class Instrument:
    """A perpetual contract. `symbol` uses ccxt unified notation, e.g. BTC/USDT:USDT."""

    symbol: str
    asset_class: AssetClass
    tick_size: float
    lot_size: float
    taker_fee: float = 0.0005
    maker_fee: float = 0.0002

    def round_price(self, price: float) -> float:
        return round(round(price / self.tick_size) * self.tick_size, 10)

    def round_qty(self, qty: float) -> float:
        return round(int(qty / self.lot_size) * self.lot_size, 10)


@dataclass
class OrderBook:
    symbol: str
    ts: float
    bids: list[tuple[float, float]]  # (price, size), best first
    asks: list[tuple[float, float]]

    @property
    def best_bid(self) -> float:
        return self.bids[0][0]

    @property
    def best_ask(self) -> float:
        return self.asks[0][0]

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid

    def imbalance(self, depth: int = 5) -> float:
        """Order book imbalance in [-1, 1]; positive means more resting bid size."""
        b = sum(s for _, s in self.bids[:depth])
        a = sum(s for _, s in self.asks[:depth])
        return 0.0 if b + a == 0 else (b - a) / (b + a)


_order_ids = itertools.count(1)


@dataclass
class Order:
    symbol: str
    side: Side
    qty: float
    price: float | None = None  # None means market order
    post_only: bool = False
    reduce_only: bool = False
    tag: str = ""
    id: str = field(default_factory=lambda: f"o{next(_order_ids)}")
    status: OrderStatus = OrderStatus.OPEN
    filled: float = 0.0
    ts: float = 0.0

    @property
    def remaining(self) -> float:
        return self.qty - self.filled

    @property
    def is_market(self) -> bool:
        return self.price is None


@dataclass(frozen=True)
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: float
    price: float
    fee: float
    ts: float
    maker: bool
