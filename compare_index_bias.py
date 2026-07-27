# -*- coding: utf-8 -*-
"""compare_index_bias.py — bias_oversold 策略 × 六大宽基指数横向对比

回答的问题：同一个"超跌抄底"策略，换别的宽基指数，数据会比上证更好吗？

公平性设计（防"拿不同条件比输赢"）：
    同一策略（bias_oversold：BIAS20≤-6% 入场，+5% 止盈 / 20 日超期）
    同一区间（2018-07 起，科创50 指数 2020 年才发布，单独标注）
    同一成本（双边 0.1%，ETF 无印花税口径）
    只换标的——这样差异才只能来自标的本身

用法：python compare_index_bias.py
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from quant.data import load_data, prepare
from quant.engine import run_backtest
from quant.report import compare_table
from quant.strategies import REGISTRY

TARGETS = ["上证指数", "沪深300", "中证500", "上证50", "创业板指", "科创50"]
START = "2018-07-01"
COST = 0.001

if __name__ == "__main__":
    strategy = REGISTRY["bias_oversold"]
    exit_fn = strategy.exit.to_fn()

    prepare(TARGETS)                      # 先批量备好数据，断网也能发现得早
    rows = []
    for q in TARGETS:
        df, info = load_data(q)
        trades, eq = run_backtest(df, strategy.entry_fn, exit_fn, start=START, cost=COST)
        n_sig = int(strategy.entry_fn(df).loc[pd.Timestamp(START):].sum())
        first = df.loc[pd.Timestamp(START):].index[0]
        rows.append((f"{info['name']}（{first:%Y-%m}起）", n_sig, trades, eq))

    compare_table(f"策略「bias_oversold」× 宽基指数对比（+5% 止盈 / 20 日超期，成本 0.1%）", rows)
