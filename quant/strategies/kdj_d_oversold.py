# -*- coding: utf-8 -*-
"""策略：KDJ 的 D < 20 抄底（实测平庸，留档作对照）
详见 Knowledge/zhihu/吃超跌恐慌修复策略.md"""
from quant import ExitSpec, Strategy
from quant.signals import sig_kdj_d_oversold

STRATEGY = Strategy(
    name="kdj_d_oversold",
    entry_fn=sig_kdj_d_oversold,         # KDJ(9,3,3) 的 D < 20 首日触发
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：胜率 76%/年化 3.2%/回撤 -10.8%（2018-07~2026-07）",
)
