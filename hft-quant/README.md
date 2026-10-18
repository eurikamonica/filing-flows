# hft-quant

面向永续合约（加密货币、商品、股票 perp）的高频量化交易框架，Python + asyncio。

> **只支持回测、纸面交易和交易所测试网。** 代码里没有实盘模式，配置文件拒绝任何像密钥的字段。策略在合成数据上的结果没有参考意义，上线前必须用真实录制数据回测并在测试网长期验证。

## 架构

```
行情 feed ──▶ Engine ──▶ PaperExchange.on_book（撮合挂单）
                 │
                 ├─▶ RiskManager.on_mark（回撤熔断）
                 ├─▶ Strategy.on_book ──▶ 下单/撤单意图
                 └─▶ RiskManager.check ──▶ Exchange.place
```

| 模块 | 作用 |
|---|---|
| `hft/models.py` | Instrument、OrderBook、Order、Fill 等数据结构，含资产类别（crypto / commodity / equity） |
| `hft/data/feeds.py` | 合成行情、ccxt.pro websocket 实时盘口（公开数据，无需密钥）、JSONL 录制与回放 |
| `hft/exchange/paper.py` | 本地撮合：吃单按对手价成交，挂单在对手价穿过后按 maker 成交，支持延迟模拟 |
| `hft/exchange/ccxt_testnet.py` | ccxt 测试网适配器，强制 sandbox 模式，密钥只从环境变量读 |
| `hft/risk.py` | 单笔/单品种/总敞口上限、价格偏离、下单频率、回撤熔断（触发后撤单并平仓） |
| `hft/strategy/market_maker.py` | 库存感知做市（Avellaneda-Stoikov 思路 + 盘口不平衡倾斜） |
| `hft/strategy/imbalance.py` | 盘口不平衡动量吃单，止盈/止损/最长持仓 |
| `hft/engine.py` | 事件循环，统计成交、拒单原因、PnL 曲线 |

## 快速开始

```bash
cd hft-quant            # 所有命令都在这个目录下运行
pip install -r requirements.txt
python -m pytest -q

# 合成数据回测（离线）
python -m hft.cli backtest --config config/example.yaml
python -m hft.cli backtest --latency 0.05          # 加 50ms 下单延迟

# 查交易所有哪些商品/股票永续，拿 tick/lot/手续费填进配置
python -m hft.cli markets --exchange binanceusdm --base XAU TSLA

# 录制真实盘口，再用录制数据回测
python -m hft.cli record --exchange binanceusdm --symbols BTC/USDT:USDT --out data/btc.jsonl --limit 50000
python -m hft.cli backtest --data data/btc.jsonl

# 纸面交易：真实行情 + 本地模拟成交
python -m hft.cli paper --config config/example.yaml

# 测试网：先把测试网密钥放进 .env（见 .env.example），再 export 到环境变量
python -m hft.cli testnet --config config/example.yaml
```

## 商品和股票永续

不同交易所上的商品（如 XAU 黄金）和股票（如 TSLA）永续合约品种、代码和交易时段差别很大，而且经常变。`config/example.yaml` 里的 XAU、TSLA 只是示例，跑 paper/testnet 之前用 `markets` 命令确认品种存在，并按实际 tick、lot、手续费修改。股票永续在美股休市时流动性和价差会明显变差，做市参数要分时段调整。

## 已知局限

- 纸面撮合不模拟排队位置和部分成交，对挂单偏乐观。
- 撤单没有延迟模拟。
- Python asyncio 的延迟在毫秒级，适合中低频的"高频"策略；真正微秒级需要 C++/Rust 和交易所托管。
