"""ccxt adapter locked to the exchange's sandbox/testnet.

Live trading is intentionally not supported here: the constructor refuses to run
unless sandbox mode is enabled. API keys are read from environment variables only
and are never written to config files or logs.
"""
from __future__ import annotations

import logging
import os

from ..models import Fill, Order, OrderStatus, Side
from .base import Exchange

log = logging.getLogger(__name__)


class CcxtTestnetExchange(Exchange):
    def __init__(self, exchange_id: str) -> None:
        super().__init__()
        import ccxt.pro as ccxtpro  # imported lazily so backtests don't need network deps

        prefix = exchange_id.upper()
        self.client = getattr(ccxtpro, exchange_id)({
            "apiKey": os.environ.get(f"{prefix}_TESTNET_API_KEY"),
            "secret": os.environ.get(f"{prefix}_TESTNET_API_SECRET"),
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        self.client.set_sandbox_mode(True)  # raises if the exchange has no testnet
        if not self.client.urls.get("test"):
            raise RuntimeError(f"{exchange_id} has no testnet; refusing to start")
        self._orders: dict[str, Order] = {}

    async def place(self, order: Order) -> Order:
        params = {"reduceOnly": order.reduce_only, "clientOrderId": order.id}
        if order.post_only:
            params["postOnly"] = True
        try:
            await self.client.create_order(
                order.symbol, "market" if order.is_market else "limit",
                order.side.value, order.qty, order.price, params,
            )
            self._orders[order.id] = order
        except Exception as e:  # exchange rejections should not crash the engine
            log.warning("order %s rejected: %s", order.id, e)
            order.status = OrderStatus.REJECTED
        return order

    async def cancel(self, order_id: str) -> None:
        o = self._orders.pop(order_id, None)
        if o:
            try:
                await self.client.cancel_order(None, o.symbol, {"clientOrderId": order_id})
                o.status = OrderStatus.CANCELED
            except Exception as e:
                log.warning("cancel %s failed: %s", order_id, e)

    def open_orders(self, symbol: str | None = None) -> list[Order]:
        return [o for o in self._orders.values() if symbol is None or o.symbol == symbol]

    async def watch_fills(self) -> None:
        """Stream private trades and forward them as Fills."""
        while True:
            for t in await self.client.watch_my_trades():
                cid = (t.get("info") or {}).get("clientOrderId") or t.get("clientOrderId") or t["order"]
                fee = (t.get("fee") or {}).get("cost") or 0.0
                self._emit_fill(Fill(cid, t["symbol"], Side(t["side"]), t["amount"], t["price"],
                                     fee, t["timestamp"] / 1000, t.get("takerOrMaker") == "maker"))
                o = self._orders.get(cid)
                if o:
                    o.filled += t["amount"]
                    if o.remaining <= 1e-12:
                        o.status = OrderStatus.FILLED
                        self._orders.pop(cid, None)

    async def close(self) -> None:
        await self.client.close()
