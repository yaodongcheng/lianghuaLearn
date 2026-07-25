# -*- coding: utf-8 -*-
"""策略：跌破 BOLL 下轨抄底（信号太频繁，实测失效——留档作反面教材）
详见 Knowledge/zhihu/吃超跌恐慌修复策略.md"""
from quant import ExitSpec, Strategy
from quant.signals import sig_boll_lower

STRATEGY = Strategy(
    name="boll_lower",
    entry_fn=sig_boll_lower,             # 收盘 < MA20 - 2σ 首日触发
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：胜率 72%/年化 4.1%/回撤 -11.4%；年均 6+ 次太常见 = 无区分度",
)
