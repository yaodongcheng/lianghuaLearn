# -*- coding: utf-8 -*-
"""策略：RSI(6) 超卖抄底（信号偏多、上证年化最高，但回撤大）
详见 Knowledge/zhihu/吃超跌恐慌修复策略.md"""
from quant import ExitSpec, Strategy
from quant.signals import sig_rsi_oversold

STRATEGY = Strategy(
    name="rsi6_oversold",
    entry_fn=sig_rsi_oversold,           # RSI(6) ≤ 20 首日触发（Wilder 平滑口径）
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：胜率 79%/年化 7.0%/回撤 -7.4%（2018-07~2026-07）",
)
