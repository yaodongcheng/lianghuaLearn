# -*- coding: utf-8 -*-
"""quant/portfolios/ — 组合策略库注册表：一套配方一个文件，这里逐个登记。
新增组合 = 新建文件 + 这里加两行（import + 名单），run.py 按 name 取用。

与 quant/strategies/（单标的择时策略）平级：run.py 填的名字在哪个注册表里，
就自动走哪个模式，所以两边的 name 不许重名（下面有断言把关）。"""
from quant.portfolios.bottom_reversal_fund import PORTFOLIO as _br
from quant.portfolios.dividend_ratio_top20 import PORTFOLIO as _div
from quant.portfolios.gold_nasdaq_2 import PORTFOLIO as _g2
from quant.portfolios.grid_3tier import PORTFOLIO as _grid
from quant.portfolios.longterm_balance import PORTFOLIO as _lt
from quant.portfolios.longterm_balance_oil import PORTFOLIO as _lt_oil
from quant.portfolios.longterm_balance_oilstock import PORTFOLIO as _lt_oils
from quant.portfolios.longterm_balance_v1 import PORTFOLIO as _lt1

_ALL = [_lt, _lt1, _lt_oil, _lt_oils, _g2, _grid, _div, _br]
REGISTRY = {p.name: p for p in _ALL}


def _assert_no_name_clash():
    """组合名与单标的策略名撞车 → run.py 分不清该走哪个模式，直接报错而不是猜。"""
    from quant.strategies import REGISTRY as STRAT
    dup = sorted(set(REGISTRY) & set(STRAT))
    if dup:
        raise RuntimeError(f"组合名与策略名重复：{dup}（请改名，run.py 按名字分派模式）")


_assert_no_name_clash()
