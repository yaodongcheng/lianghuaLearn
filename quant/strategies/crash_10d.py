# -*- coding: utf-8 -*-
"""策略：10 日急跌抄底（v3 实测胜率之王，信号最稀）
详见 Knowledge/zhihu/吃超跌恐慌修复策略.md"""
from quant import ExitSpec, Strategy
from quant.signals import sig_crash

STRATEGY = Strategy(
    name="crash_10d",
    entry_fn=sig_crash,                  # 10 日收益率 ≤ -7% 首日触发
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：10 笔/胜率 90%/年化 4.0%/回撤 -5.2%（2018-07~2026-07）",
)
