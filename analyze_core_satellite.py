# -*- coding: utf-8 -*-
"""analyze_core_satellite.py — 计划13：核心-卫星组合回测（可重跑）

验证 Knowledge/hybrid_vs_core_satellite.md 的终极结论：
"一直在场 + 恐慌增强"是唯一没被数据否决的结构。

做法（口径见 plans/13）：
- 核心仓：期初一次买入上证并持有（不再动）
- 卫星仓：独立账户跑 bottom_reversal（引擎原版回测，T+1/成本/冷却全保留）
- 组合净值 = w·核心净值 + (1-w)·卫星净值（分开记账、中途不划转）
- 卫星空仓期现金收益按 0 计（保守口径）
产出：终端对比表 + data/core_satellite_000001.png（净值图，标三次牛市色带）
"""
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fetch_data import DATA_DIR
from quant import metrics, run_backtest
from quant.data import load_data
from quant.strategies.bottom_reversal import STRATEGY as br

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

START = "2018-07-01"
COST = 0.001
# 上证三次牛市（知识库第四轮分类）：恐慌底 / 尖峰 / 慢牛
BULLS = [("2019-01-04", "2019-04-08", "恐慌底牛市"),
         ("2024-09-18", "2024-10-08", "尖峰牛市"),
         ("2025-04-08", "2025-11-13", "慢牛")]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    df, info = load_data("上证指数")
    trades, eq_sat = run_backtest(df, br.entry_fn, br.exit_fn(),
                                  start=START, cost=COST)
    bt = df.loc[START:]
    eq_core = bt["close"] / bt["close"].iloc[0]

    # —— 权重敏感性：净值加权（漂移不再平衡）——
    rows = []
    for w_core in (1.0, 0.8, 0.7, 0.5, 0.0):
        port = w_core * eq_core + (1 - w_core) * eq_sat
        rows.append({
            "组合": f"{w_core:.0%}核心+{1-w_core:.0%}卫星",
            "总收益": port.iloc[-1] - 1,
            "年化": metrics.annual_return(port),
            "最大回撤": metrics.max_drawdown(port),
            "夏普": metrics.sharpe_ratio(port),
        })
    print(f"核心-卫星组合回测：上证指数（{bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}）")
    print(f"{'组合':<16}{'总收益':>8}{'年化':>8}{'最大回撤':>9}{'夏普':>7}")
    for r in rows:
        print(f"{r['组合']:<16}{r['总收益']:>+8.1%}{r['年化']:>+8.1%}"
              f"{r['最大回撤']:>9.1%}{r['夏普']:>7.2f}")
    print("※ 卫星空仓期现金收益按 0 计（实际放货基约 +1.5%/年，组合只会更好）")

    # —— 图：净值对比 + 三次牛市色带 + 回撤子图 ——
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
    for d0, d1, label in BULLS:
        ax1.axvspan(pd.Timestamp(d0), pd.Timestamp(d1), color="red", alpha=0.08)
        ax1.text(pd.Timestamp(d0), 1.02, label, transform=ax1.get_xaxis_transform(),
                 fontsize=8, color="red", va="bottom")
    ax1.plot(eq_core.index, eq_core, color="0.55", lw=1.2,
             label="100% 持有（纯核心）")
    ax1.plot(eq_sat.index, eq_sat, color="steelblue", lw=1.2,
             label="100% bottom_reversal（纯卫星）")
    port70 = 0.7 * eq_core + 0.3 * eq_sat
    ax1.plot(port70.index, port70, color="red", lw=1.6,
             label="70% 核心 + 30% 卫星")
    ax1.set_title("核心-卫星组合 vs 纯持有 vs 纯超跌策略（上证指数，净值起点=1）")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)

    for s, c, lab in [(eq_core, "0.55", "纯持有"), (port70, "red", "70/30 组合")]:
        dd = s / s.cummax() - 1
        ax2.fill_between(dd.index, dd, 0, color=c, alpha=0.35, label=lab)
    ax2.set_ylabel("回撤")
    ax2.legend(loc="lower left", fontsize=8)
    ax2.grid(alpha=0.25)

    out = DATA_DIR / "core_satellite_000001.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"📊 图已保存：{out}")


if __name__ == "__main__":
    main()
