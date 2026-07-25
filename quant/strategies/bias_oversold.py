# -*- coding: utf-8 -*-
"""策略：BIAS 超跌抄底（知乎策略验证 v3 实测综合最佳）
详见 Knowledge/zhihu/吃超跌恐慌修复策略.md"""
from quant import ExitSpec, Strategy
from quant.signals import sig_bias_oversold

STRATEGY = Strategy(
    name="bias_oversold",
    entry_fn=sig_bias_oversold,          # BIAS20 ≤ -6% 首日触发（库信号，默认参数即 v3 口径）
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：9 笔/胜率 89%/年化 4.6%/回撤 -5.3%（2018-07~2026-07）",
)
