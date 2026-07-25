# -*- coding: utf-8 -*-
"""策略：MA5 上穿 MA20 金叉（趋势跟踪演示）——plans/07 验收用例：
"新入场信号从写函数到完整报告 ≤10 行"，本文件就是答案（核心逻辑 2 行）。"""
from quant import Strategy
from quant.exits import exit_below_ma
from quant.indicators import cal_ma
from quant.signals import cross_down


def entry(df):
    return cross_down(cal_ma(df["close"], 5) > cal_ma(df["close"], 20))   # 金叉首日


STRATEGY = Strategy(
    name="ma_cross",
    entry_fn=entry,
    exit=exit_below_ma(20),              # 跌破 MA20 离场（现成函数，演示离场插槽）
    note="演示用：金叉策略在震荡市会被反复打脸，别直接当真钱策略",
)
