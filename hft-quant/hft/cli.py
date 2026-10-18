"""Command line entry point.

  python -m hft.cli backtest --config config/example.yaml
  python -m hft.cli paper    --config config/example.yaml   # live public data, simulated fills
  python -m hft.cli testnet  --config config/example.yaml   # exchange testnet, keys from env
  python -m hft.cli markets  --exchange binanceusdm --base XAU TSLA
  python -m hft.cli record   --exchange binanceusdm --symbols BTC/USDT:USDT --out data/btc.jsonl --limit 50000
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from . import config as cfgmod
from .data import feeds
from .engine import Engine, Stats
from .exchange.paper import PaperExchange
from .portfolio import Portfolio
from .risk import RiskManager
from .strategy.registry import STRATEGIES


def build(cfg: cfgmod.Config, exchange):
    portfolio = Portfolio()
    risk = RiskManager(cfg.risk, portfolio)
    strategies = {ic.instrument.symbol: STRATEGIES[ic.strategy](ic.instrument, **ic.params) for ic in cfg.instruments}
    return Engine(exchange, strategies, risk, portfolio)


def report(engine: Engine, stats: Stats) -> None:
    print(f"books={stats.books} orders={stats.orders} fills={stats.fills} "
          f"(maker {stats.maker_fills}) volume={stats.volume:,.2f}")
    if stats.rejects:
        print("risk/exchange rejects:", stats.rejects)
    for sym, p in engine.portfolio.positions.items():
        print(f"  {sym:<20} qty={p.qty:+.6f} realized={p.realized:+.4f} fees={p.fees:.4f}")
    print(f"total PnL (after fees) = {engine.portfolio.equity_pnl(engine.marks):+.4f}")
    if engine.risk.killed:
        print("kill switch fired:", engine.risk.kill_reason)


async def run(args) -> None:
    cfg = cfgmod.load(args.config)
    insts = {ic.instrument.symbol: ic.instrument for ic in cfg.instruments}
    symbols = list(insts)

    if args.cmd == "backtest":
        if args.data:
            feed = feeds.jsonl_feed(args.data)
        else:
            feed = feeds.synthetic_feed(list(insts.values()),
                                        {ic.instrument.symbol: ic.start_price for ic in cfg.instruments},
                                        steps=args.steps or cfg.backtest_steps)
        engine = build(cfg, PaperExchange(insts, latency=args.latency))
        report(engine, await engine.run(feed))
    elif args.cmd == "paper":
        engine = build(cfg, PaperExchange(insts, latency=args.latency))
        report(engine, await engine.run(feeds.ccxt_ws_feed(cfg.exchange, symbols), max_books=args.max_books))
    elif args.cmd == "testnet":
        from .exchange.ccxt_testnet import CcxtTestnetExchange
        ex = CcxtTestnetExchange(cfg.exchange)
        engine = build(cfg, ex)
        fills = asyncio.create_task(ex.watch_fills())
        try:
            report(engine, await engine.run(feeds.ccxt_ws_feed(cfg.exchange, symbols, sandbox=True),
                                            max_books=args.max_books))
        finally:
            fills.cancel()
            await ex.close()


async def list_markets(exchange_id: str, bases: list[str]) -> None:
    import ccxt.async_support as ccxt
    c = getattr(ccxt, exchange_id)({"options": {"defaultType": "swap"}})
    try:
        markets = await c.load_markets()
        for s, m in sorted(markets.items()):
            if m.get("swap") and (not bases or m["base"] in bases):
                print(f"{s:<28} tick={m['precision'].get('price')} lot={m['precision'].get('amount')} "
                      f"taker={m.get('taker')} maker={m.get('maker')}")
    finally:
        await c.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="hft")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("backtest", "paper", "testnet"):
        sp = sub.add_parser(name)
        sp.add_argument("--config", default="config/example.yaml")
        sp.add_argument("--latency", type=float, default=0.0, help="simulated order latency, seconds")
        sp.add_argument("--max-books", type=int, default=None)
        if name == "backtest":
            sp.add_argument("--data", help="JSONL file from `record`; synthetic data if omitted")
            sp.add_argument("--steps", type=int, default=None)
    mk = sub.add_parser("markets")
    mk.add_argument("--exchange", default="binanceusdm")
    mk.add_argument("--base", nargs="*", default=[])
    rec = sub.add_parser("record")
    rec.add_argument("--exchange", default="binanceusdm")
    rec.add_argument("--symbols", nargs="+", required=True)
    rec.add_argument("--out", required=True)
    rec.add_argument("--limit", type=int, default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "markets":
        asyncio.run(list_markets(args.exchange, args.base))
    elif args.cmd == "record":
        n = asyncio.run(feeds.record(feeds.ccxt_ws_feed(args.exchange, args.symbols), args.out, args.limit))
        print(f"recorded {n} books to {args.out}")
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
