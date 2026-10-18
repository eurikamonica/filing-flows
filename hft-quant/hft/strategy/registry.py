from .imbalance import ImbalanceTaker
from .market_maker import MarketMaker

STRATEGIES = {cls.name: cls for cls in (MarketMaker, ImbalanceTaker)}
