# -*- coding: utf-8 -*-
"""quant/strategies/ — 策略库注册表：一套打法一个文件，这里逐个登记。
新增策略 = 新建文件 + 这里加两行（import + 名单），run.py 按 name 取用。"""
from quant.strategies.bias_oversold import STRATEGY as _bias
from quant.strategies.boll_lower import STRATEGY as _boll
from quant.strategies.crash_10d import STRATEGY as _crash
from quant.strategies.drawdown_60d import STRATEGY as _dd
from quant.strategies.kdj_d_oversold import STRATEGY as _kdj
from quant.strategies.ma_cross import STRATEGY as _ma
from quant.strategies.rsi6_oversold import STRATEGY as _rsi

_ALL = [_bias, _boll, _crash, _dd, _kdj, _ma, _rsi]
REGISTRY = {s.name: s for s in _ALL}
