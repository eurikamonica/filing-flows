import asyncio

import pytest

from hft import config as cfgmod
from hft.engine import Engine
from hft.exchange.paper import PaperExchange
from hft.models import AssetClass, Fill, Instrument, Order, OrderBook, Side
from hft.portfolio import Portfolio, Position
from hft.risk import RiskLimits, RiskManager
from hft.strategy.market_maker import MarketMaker

BTC = Instrument("BTC/USDT:USDT", AssetClass.CRYPTO, tick_size=0.1, lot_size=0.001)


def book(bid, ask, ts=0.0, bid_sz=1.0, ask_sz=1.0):
    return OrderBook(BTC.symbol, ts, [(bid, bid_sz)], [(ask, ask_sz)])


def fill(side, qty, px, fee=0.0):
    return Fill("x", BTC.symbol, side, qty, px, fee, 0.0, True)


def test_position_round_trip_and_flip():
    p = Position(BTC.symbol)
    p.apply(fill(Side.BUY, 2, 100))
    p.apply(fill(Side.BUY, 2, 110))
    assert p.qty == 4 and p.avg_price == pytest.approx(105)
    p.apply(fill(Side.SELL, 6, 120))  # close 4 at +15, open short 2 at 120
    assert p.realized == pytest.approx(60)
    assert p.qty == -2 and p.avg_price == 120


def test_paper_exchange_maker_and_taker_fills():
    ex = PaperExchange({BTC.symbol: BTC})
    fills = []
    ex.on_fill(fills.append)
    ex.on_book(book(100.0, 100.2))
    asyncio.run(ex.place(Order(BTC.symbol, Side.BUY, 0.01, 100.0)))
    assert not fills  # rests at the bid
    ex.on_book(book(99.8, 100.0, ts=1))  # ask trades down to our price
    assert len(fills) == 1 and fills[0].maker and fills[0].price == 100.0
    asyncio.run(ex.place(Order(BTC.symbol, Side.SELL, 0.01)))  # market
    assert len(fills) == 2 and not fills[1].maker and fills[1].price == 99.8


def test_post_only_crossing_order_is_rejected():
    ex = PaperExchange({BTC.symbol: BTC})
    ex.on_book(book(100.0, 100.2))
    o = asyncio.run(ex.place(Order(BTC.symbol, Side.BUY, 0.01, 100.2, post_only=True)))
    assert o.status.value == "rejected"


def test_risk_limits():
    pf = Portfolio()
    risk = RiskManager(RiskLimits(max_position_notional=50, max_order_notional=40,
                                  max_price_deviation=0.01, max_orders_per_sec=2), pf)
    mid = 100.0
    assert risk.check(Order(BTC.symbol, Side.BUY, 1, 90), mid, {}, now=0) == "price too far from mid"
    assert risk.check(Order(BTC.symbol, Side.BUY, 0.5, 100), mid, {}, now=0) == "order notional too large"
    assert risk.check(Order(BTC.symbol, Side.BUY, 0.3, 100), mid, {}, now=0) is None
    assert risk.check(Order(BTC.symbol, Side.BUY, 0.3, 100), mid, {}, now=0) is None
    assert risk.check(Order(BTC.symbol, Side.BUY, 0.1, 100), mid, {}, now=0.5) == "order rate limit"
    pf.on_fill(fill(Side.BUY, 0.4, 100))
    assert risk.check(Order(BTC.symbol, Side.BUY, 0.2, 100), mid, {}, now=5) == "position limit"
    assert risk.check(Order(BTC.symbol, Side.BUY, 0.1, reduce_only=True), mid, {}, now=5) is not None
    assert risk.check(Order(BTC.symbol, Side.SELL, 0.2, 100), mid, {}, now=5) is None


def test_kill_switch_on_drawdown():
    pf = Portfolio()
    risk = RiskManager(RiskLimits(max_drawdown=5), pf)
    pf.on_fill(fill(Side.BUY, 1, 100))
    risk.on_mark({BTC.symbol: 101})
    risk.on_mark({BTC.symbol: 95})
    assert risk.killed
    assert risk.check(Order(BTC.symbol, Side.SELL, 0.1, 95), 95, {}) .startswith("killed")


def test_market_maker_skews_against_inventory():
    mm = MarketMaker(BTC, order_qty=0.001, max_inventory=0.01, imbalance_weight=0)
    b = OrderBook(BTC.symbol, 0, [(100.0, 1)], [(101.0, 1)])
    flat = mm.on_book(b, Position(BTC.symbol), [])
    long_pos = Position(BTC.symbol, qty=0.009, avg_price=100.5)
    skewed = MarketMaker(BTC, order_qty=0.001, max_inventory=0.01, imbalance_weight=0).on_book(b, long_pos, [])
    px = lambda acts, side: next(o.price for o in acts.place if o.side is side)
    assert px(skewed, Side.SELL) <= px(flat, Side.SELL)
    assert px(skewed, Side.BUY) <= px(flat, Side.BUY)
    at_limit = Position(BTC.symbol, qty=0.01)
    assert all(o.side is Side.SELL for o in mm.on_book(b, at_limit, []).place)


def test_config_rejects_secrets_and_live_mode(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("mode: backtest\ninstruments: []\napi_key: abc\n")
    with pytest.raises(ValueError, match="credential"):
        cfgmod.load(p)
    p.write_text("mode: live\ninstruments: []\n")
    with pytest.raises(ValueError, match="live trading"):
        cfgmod.load(p)


def test_example_config_backtest_runs():
    from hft.cli import build
    from hft.data.feeds import synthetic_feed
    cfg = cfgmod.load("config/example.yaml")
    insts = {ic.instrument.symbol: ic.instrument for ic in cfg.instruments}
    engine: Engine = build(cfg, PaperExchange(insts))
    feed = synthetic_feed(list(insts.values()), {ic.instrument.symbol: ic.start_price for ic in cfg.instruments},
                          steps=500)
    stats = asyncio.run(engine.run(feed))
    assert stats.books == 1500 and stats.orders > 0
    assert not engine.exchange.open_orders()


def test_tardis_csv_feed_merges_maps_and_dedupes(tmp_path):
    import gzip
    from hft.data import feeds

    hdr = "exchange,symbol,timestamp,local_timestamp," + ",".join(
        f"{s}[{k}].{f}" for k in range(2) for s in ("asks", "bids") for f in ("price", "amount"))
    btc = tmp_path / "BTCUSDT.csv.gz"
    with gzip.open(btc, "wt") as f:
        f.write(hdr + "\n")
        f.write("binance-futures,BTCUSDT,1000000,0,100.1,1,100.0,2,100.2,1,99.9,1\n")
        f.write("binance-futures,BTCUSDT,3000000,0,100.1,1,100.0,2,100.2,1,99.9,1\n")  # duplicate top
        f.write("binance-futures,BTCUSDT,4000000,0,100.2,1,100.1,2,100.3,1,100.0,1\n")
    xau = tmp_path / "XAUUSDT.csv"
    xau.write_text(hdr + "\nbinance-futures,XAUUSDT,2000000,0,2600.1,1,2600.0,1,,,2599.9,1\n")

    async def collect():
        return [b async for b in feeds.tardis_csv_feed([btc, xau], [BTC.symbol, "XAU/USDT:USDT"], depth=2)]

    books = asyncio.run(collect())
    assert [(b.symbol, b.ts) for b in books] == [
        (BTC.symbol, 1.0), ("XAU/USDT:USDT", 2.0), (BTC.symbol, 4.0)]
    assert books[0].bids == [(100.0, 2.0), (99.9, 1.0)]
    assert books[1].asks == [(2600.1, 1.0)]
