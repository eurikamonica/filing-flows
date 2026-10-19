"""Load YAML config into typed objects. Config files must never contain API keys."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml

from .models import AssetClass, Instrument
from .risk import RiskLimits

FORBIDDEN_KEYS = {"apikey", "api_key", "secret", "api_secret", "password", "private_key"}


@dataclass
class InstrumentConfig:
    instrument: Instrument
    strategy: str
    params: dict
    start_price: float


@dataclass
class Config:
    mode: str  # backtest | paper | testnet
    exchange: str
    instruments: list[InstrumentConfig]
    risk: RiskLimits
    backtest_steps: int = 20_000


def _check_no_secrets(node, path="") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"config key '{path}{k}' looks like a credential; use environment variables")
            _check_no_secrets(v, f"{path}{k}.")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _check_no_secrets(v, f"{path}{i}.")


def load(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text())
    _check_no_secrets(raw)
    mode = raw.get("mode", "backtest")
    if mode not in {"backtest", "paper", "testnet"}:
        raise ValueError(f"unsupported mode {mode!r}; live trading is not enabled in this project")
    insts = []
    for d in raw["instruments"]:
        inst = Instrument(
            symbol=d["symbol"], asset_class=AssetClass(d["asset_class"]),
            tick_size=float(d["tick_size"]), lot_size=float(d["lot_size"]),
            taker_fee=float(d.get("taker_fee", 0.0005)), maker_fee=float(d.get("maker_fee", 0.0002)),
        )
        insts.append(InstrumentConfig(inst, d["strategy"], d.get("params", {}), float(d.get("start_price", 100))))
    allowed = {f.name for f in fields(RiskLimits)}
    risk = RiskLimits(**{k: v for k, v in (raw.get("risk") or {}).items() if k in allowed})
    return Config(mode, raw.get("exchange", "binanceusdm"), insts, risk, int(raw.get("backtest_steps", 20_000)))
