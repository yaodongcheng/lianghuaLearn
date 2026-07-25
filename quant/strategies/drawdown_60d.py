# -*- coding: utf-8 -*-
"""策略：60 日高点回撤 ≥8% 抄底（慢半拍，容易接阴跌飞刀——留档作对照）
详见 Knowledge/zhihu/吃超跌恐慌修复策略.md"""
from quant import ExitSpec, Strategy
from quant.signals import sig_drawdown

STRATEGY = Strategy(
    name="drawdown_60d",
    entry_fn=sig_drawdown,               # 距 60 日高点回撤 ≥8% 首日触发
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：胜率 71%/年化 4.3%/回撤 -11.7%（2018-07~2026-07）",
)
