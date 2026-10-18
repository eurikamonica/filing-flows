"""Market data feeds. Each feed is an async iterator of OrderBook snapshots."""
from __future__ import annotations

import asyncio
import json
import math
import random
from pathlib import Path
from typing import AsyncIterator

from ..models import Instrument, OrderBook


async def synthetic_feed(instruments: list[Instrument], start_prices: dict[str, float],
                         steps: int, dt: float = 0.1, vol: float = 0.6,
                         seed: int = 7) -> AsyncIterator[OrderBook]:
    """Random-walk books for offline testing. `vol` is annualised volatility."""
    rng = random.Random(seed)
    mids = dict(start_prices)
    sigma = vol * math.sqrt(dt / (365 * 24 * 3600))
    for i in range(steps):
        ts = i * dt
        for inst in instruments:
            mids[inst.symbol] *= math.exp(sigma * rng.gauss(0, 1) * 20)
            mid = mids[inst.symbol]
            half = inst.tick_size * rng.randint(1, 3)
            bid = inst.round_price(mid - half)
            ask = max(inst.round_price(mid + half), bid + inst.tick_size)
            yield OrderBook(
                inst.symbol, ts,
                [(bid - k * inst.tick_size, rng.uniform(0.5, 5)) for k in range(5)],
                [(ask + k * inst.tick_size, rng.uniform(0.5, 5)) for k in range(5)],
            )


async def ccxt_ws_feed(exchange_id: str, symbols: list[str], depth: int = 10,
                       sandbox: bool = False) -> AsyncIterator[OrderBook]:
    """Live public order books over websocket (no API key needed, read-only)."""
    import ccxt.pro as ccxtpro

    client = getattr(ccxtpro, exchange_id)({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    if sandbox:
        client.set_sandbox_mode(True)
    queue: asyncio.Queue[OrderBook] = asyncio.Queue(maxsize=10_000)

    async def pump(symbol: str) -> None:
        while True:
            ob = await client.watch_order_book(symbol, depth)
            book = OrderBook(symbol, (ob["timestamp"] or client.milliseconds()) / 1000,
                             [(p, s) for p, s, *_ in ob["bids"][:depth]],
                             [(p, s) for p, s, *_ in ob["asks"][:depth]])
            if book.bids and book.asks:
                if queue.full():
                    queue.get_nowait()  # drop stale data rather than fall behind
                queue.put_nowait(book)

    tasks = [asyncio.create_task(pump(s)) for s in symbols]
    try:
        while True:
            yield await queue.get()
    finally:
        for t in tasks:
            t.cancel()
        await client.close()


async def jsonl_feed(path: str | Path) -> AsyncIterator[OrderBook]:
    """Replay books recorded by `record`."""
    with open(path) as f:
        for line in f:
            d = json.loads(line)
            yield OrderBook(d["symbol"], d["ts"], [tuple(x) for x in d["bids"]], [tuple(x) for x in d["asks"]])


async def record(feed: AsyncIterator[OrderBook], path: str | Path, limit: int | None = None) -> int:
    n = 0
    with open(path, "a") as f:
        async for b in feed:
            f.write(json.dumps({"symbol": b.symbol, "ts": b.ts, "bids": b.bids, "asks": b.asks}) + "\n")
            n += 1
            if limit and n >= limit:
                break
    return n
