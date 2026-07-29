# -*- coding: utf-8 -*-
"""答疑脚本：两个问题用数据说话

Q2 素材：2026 上半年沪深300 涨了多少（策略 +1.2% 该跟谁比）
Q3 素材：把四条腿的权重按 10% 步长全组合扫描（286 种），
        分别找 2013~2019 / 2020~2026 两段里"夏普最高"的权重，
        看"最优解"稳不稳定、放到样本外行不行。

口径：固定权重、每日再平衡、不计成本（教学演示，对比权重用，不复现策略的 0.98）。
跑法：python analysis/analyze_sharpe_scan.py
"""
import sys
import itertools

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from quant.portfolios.longterm_balance import PORTFOLIO
from quant.portfolio_data import load_portfolio_navs, align_prices
from quant.metrics import sharpe_ratio
from quant.data import load_data

# ---------- Q2 素材：沪深300 的 2026 年 ----------
try:
    bench, _info = load_data("沪深300", start="20260101")
    b = bench["close"]
    print(f"【Q2】沪深300 2026 年至 {b.index[-1]:%m-%d}：{b.iloc[-1] / b.iloc[0] - 1:+.1%}"
          f"（同期 longterm_balance +1.2%）\n")
except Exception as e:
    print(f"【Q2】沪深300 取数失败（不影响主结论）：{e}\n")

# ---------- Q3 素材：权重扫描 ----------
nav_map = load_portfolio_navs(PORTFOLIO.holdings, data_start=PORTFOLIO.data_start)
px, first_full = align_prices(nav_map)
ret = px.pct_change().dropna()
names = list(px.columns)

COMBOS = [np.array(c) / 100 for c in
          itertools.product(range(0, 101, 10), repeat=4) if sum(c) == 100]


def eq_of(w, r):
    """固定权重每日再平衡的净值曲线（演示口径：忽略成本与 T+1）。"""
    return pd.Series((1 + r.values @ w).cumprod(), index=r.index)


def scan(r):
    scored = sorted(((sharpe_ratio(eq_of(w, r)), w) for w in COMBOS),
                    key=lambda x: -x[0])
    return scored


P1, P2 = ret.loc[:"2019-12-31"], ret.loc["2020-01-01":]
s1, s2 = scan(P1), scan(P2)
eq_w = np.array([0.25] * 4)

print(f"【Q3】权重扫描（10% 步长，共 {len(COMBOS)} 种，夏普口径 rf=3%）")
for label, scored, r in [("2013-08~2019-12", s1, P1), ("2020-01~2026-07", s2, P2)]:
    print(f"\n— {label} 夏普前 3 名 —")
    for sh, w in scored[:3]:
        print(f"  夏普 {sh:.2f}  {dict(zip(names, (w * 100).astype(int)))}")
    print(f"  等权 25/25/25/25 夏普：{sharpe_ratio(eq_of(eq_w, r)):.2f}"
          f"（在 {len(COMBOS)} 种里排第 "
          f"{sum(1 for sh, _ in scored if sh > sharpe_ratio(eq_of(eq_w, r))) + 1}）")

# 关键一步：用前 7 年选出的"最优权重"，放到后 6.5 年（样本外）看表现
best1 = s1[0][1]
print(f"\n— 样本外检验：按 2013~2019 选出的最优权重 "
      f"{dict(zip(names, (best1 * 100).astype(int)))} —")
print(f"  它在 2013~2019（样本内）夏普：{s1[0][0]:.2f}")
print(f"  它在 2020~2026（样本外）夏普：{sharpe_ratio(eq_of(best1, P2)):.2f}")
print(f"  等权在 2020~2026（样本外）夏普：{sharpe_ratio(eq_of(eq_w, P2)):.2f}")
