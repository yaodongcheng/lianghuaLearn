# -*- coding: utf-8 -*-
"""答疑脚本：longterm_balance 的年化 11% 是"每年都有"还是"最近几年拉起来的"？

跑法：python analysis/analyze_ltb_yearly.py
口径：完全复用框架（quant/portfolio.py 引擎 + 配方文件的 decide_fn），与 run.py 一致；
     逐年收益 = 该年最后一个交易日总资产 / 上一年最后一个交易日总资产 − 1。
注意：2013 年（8 月起）与 2026 年（到 7 月）是不完整年份，表里单独标注。
"""
import sys

import pandas as pd

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")   # 与 run.py 同：框架里有 ✓ 等字符，GBK 控制台会崩
from quant.portfolios.longterm_balance import PORTFOLIO
from quant.portfolio import run_portfolio_backtest
from quant.portfolio_data import load_portfolio_navs

pd.set_option("display.unicode.east_asian_width", True)

COST, INITIAL = 0.001, 10000.0

nav_map = load_portfolio_navs(PORTFOLIO.holdings, data_start=PORTFOLIO.data_start)
eq, weights, log = run_portfolio_backtest(nav_map, PORTFOLIO.decide_fn,
                                          start=None, cost=COST, initial_cash=INITIAL)
px = weights.attrs["prices"]          # 对齐后的各腿净值（引擎归因原料）


def yearly_ret(s: pd.Series) -> pd.Series:
    """日序列 → 逐年收益（首段从序列首行算起）。"""
    last = s.groupby(s.index.year).last()
    r = last.pct_change()
    r.iloc[0] = last.iloc[0] / s.iloc[0] - 1
    return r


tbl = pd.DataFrame({"组合": yearly_ret(eq)})
for n in px.columns:
    tbl[n] = yearly_ret(px[n])

# 期末总资产放在表里，方便看"钱是在哪几年翻上去的"
tbl["期末总资产"] = eq.groupby(eq.index.year).last()

note = {2013: "（8月起）", 2026: "（到7月）"}
print(f"回测区间：{eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}，"
      f"本金 {INITIAL:.0f} 元，双边各 0.1% 成本")
print(f"{'年份':<6}{'组合':>8}{'纳指':>8}{'中证红利':>8}{'黄金':>8}{'中债':>8}{'期末总资产':>10}")
for y, row in tbl.iterrows():
    print(f"{y}{note.get(y, ''):<4}"
          f"{row['组合']:>8.1%}{row['纳指']:>8.1%}{row['中证红利']:>8.1%}"
          f"{row['黄金']:>8.1%}{row['中债综合']:>8.1%}{row['期末总资产']:>10.0f}")

# 分段汇总：钱到底在哪几年赚的（按总资产净增量，不是收益率相加）
print("\n—— 分段看：总资产每段净增多少（元）——")
year_end = eq.groupby(eq.index.year).last()
segs = [(2013, 2018), (2019, 2021), (2022, 2023), (2024, 2026)]
prev = INITIAL
for a, b in segs:
    cur = year_end.loc[b]
    print(f"{a}~{b} 年：{prev:>7.0f} → {cur:>7.0f}，净增 {cur - prev:>+7.0f} 元")
    prev = cur
print(f"合计：{INITIAL:.0f} → {eq.iloc[-1]:.0f}，净增 {eq.iloc[-1] - INITIAL:+.0f} 元"
      f"（总盈亏 {eq.iloc[-1] / INITIAL - 1:+.1%}，年化见 run.py 报告）")
