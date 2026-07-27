# -*- coding: utf-8 -*-
"""quant/strategies/ — 策略库注册表：一套打法一个文件，这里逐个登记。
新增策略 = 新建文件 + 这里加两行（import + 名单），run.py 按 name 取用。"""
from quant.strategies.bias_oversold import STRATEGY as _bias
from quant.strategies.boll_lower import STRATEGY as _boll
from quant.strategies.bottom_reversal import STRATEGY as _rev
from quant.strategies.bull_bear_hybrid import STRATEGY as _hybrid
from quant.strategies.crash_10d import STRATEGY as _crash
from quant.strategies.drawdown_60d import STRATEGY as _dd
from quant.strategies.kdj_d_oversold import STRATEGY as _kdj
from quant.strategies.ma_cross import STRATEGY as _ma
from quant.strategies.macd_cross import STRATEGY as _macd
from quant.strategies.rsi6_oversold import STRATEGY as _rsi
from quant.strategies.trend_ma250 import STRATEGY as _trend

_ALL = [_bias, _boll, _rev, _hybrid, _crash, _dd, _kdj, _ma, _macd, _rsi, _trend]
REGISTRY = {s.name: s for s in _ALL}
