# -*- coding: utf-8 -*-
"""analysis/analyze_bottom_vol.py — plans/14：bottom_reversal 在不同波动率标的上的横测

问题来源（2026-07-27 用户提问）：上证实测 21 笔/胜率 62%/年化 5.1%，用户觉得不够好，
提出假设——"底部反包策略是不是更适合波动大的标的？"

验证方法（防过拟合纪律，重要）：
- 策略参数【原样不动】（RSI6≤25 + 当日涨幅≥1% 确认；+7%/30日 离场）。
  参数本来就是在上证上提炼的，换标的后再调参 = 第二次看答案编规则，横测就没意义了。
- 波动率不凭印象，用数据算：日收益率标准差 × √244（年化）。
- 全部标的同一回测窗口 2018-07~2026-07；上市晚的标的（科创50/半导体ETF）区间短，
  表里如实标注实际区间，年化指标可横向比但样本更薄。

用法：python analysis/analyze_bottom_vol.py
（首次跑会自动下载缺失的 ETF 数据；产出 data/bottom_vol_fit.png）
"""
import sys
from pathlib import Path

# 脚本位于 analysis/ 子目录：Python 只把【脚本所在目录】加进 import 路径，
# 不会加项目根目录——手动补上，否则 from quant... / fetch_data 全部找不到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import matplotlib

sys.stdout.reconfigure(encoding="utf-8")   # Windows 控制台默认 GBK，✓ 等字符会炸（同 run.py）

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from quant import metrics
from quant.data import load_data
from quant.engine import run_backtest_ex
from quant.strategies import REGISTRY

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

START = "2018-07-01"     # 与 run.py 同口径
COST = 0.001             # 双边各 0.1%（ETF 无印花税口径）

# 波动率梯度标的：低 → 高（预期，实际以数据算出来的为准）
TARGETS = [
    "上证指数", "沪深300", "中证500", "创业板指", "科创50",
    "512480",   # 半导体ETF（行业基代表，支付宝半导体场外基跟踪的就是这类指数）
    "512880",   # 证券ETF（高 beta 行业基代表）
]

# ETF 必须前复权：512480 历史上有两次份额拆分（1拆2），raw 价出现 -48.9%/-50.7%
# 假暴跌（2026-07-27 本脚本数据体检抓出），会污染 RSI 信号和回撤统计。
# 指数无复权概念，不在此表。
ETF_ADJUST = {"512480": "qfq", "512880": "qfq"}


def annualized_vol(close):
    """年化波动率 = 日收益率标准差 × √244（A股一年约 244 个交易日）。"""
    return close.pct_change().std() * np.sqrt(244)


def bh_annual(close):
    """买入持有的年化收益（对照组口径，与策略年化同窗口）。"""
    total = close.iloc[-1] / close.iloc[0] - 1
    years = len(close) / 244
    return (1 + total) ** (1 / years) - 1


def main():
    strategy = REGISTRY["bottom_reversal"]
    exit_fn = strategy.exit.to_fn()

    rows = []
    for target in TARGETS:
        df, info = load_data(target, start="20180101",
                             adjust=ETF_ADJUST.get(target))   # 含指标预热段，同 run.py
        bt = df.loc[pd.Timestamp(START):]
        trades, eq, _ = run_backtest_ex(df, strategy.entry_fn, exit_fn,
                                        start=START, cost=COST)
        s = metrics.summarize(trades, eq)
        rows.append({
            "标的": info["name"],
            "代码": info["code"],
            "实际起点": bt.index[0],
            "年化波动率": annualized_vol(bt["close"]),
            "交易数": s["交易数"],
            "胜率": s["胜率"],
            "平均每笔": s["平均每笔"],
            "策略年化": s["年化"],
            "最大回撤": s["最大回撤"],
            "持有年化": bh_annual(bt["close"]),
        })

    # 按波动率升序排：从左到右读"波动越大，策略是否越好"
    rows.sort(key=lambda r: r["年化波动率"])

    # ---------- 文字表 ----------
    print(f"\n{'=' * 96}")
    print(f"bottom_reversal 多标的横测（参数原样不动：RSI6≤25 + 涨≥1% 确认；+7%/30日 离场；成本 {COST:.1%}）")
    print(f"{'=' * 96}")
    head = (f"{'标的':<10}{'区间起点':<12}{'年化波动':>8}{'交易数':>6}{'胜率':>7}"
            f"{'平均每笔':>9}{'策略年化':>9}{'最大回撤':>9}{'持有年化':>9}")
    print(head)
    print("-" * 96)
    for r in rows:
        win = f"{r['胜率']:.0%}" if r["交易数"] else "—"
        avg = f"{r['平均每笔']:+.1%}" if r["交易数"] else "—"
        print(f"{r['标的']:<10}{r['实际起点']:%Y-%m-%d}  {r['年化波动率']:>8.1%}"
              f"{r['交易数']:>6}{win:>7}{avg:>9}{r['策略年化']:>+9.1%}"
              f"{r['最大回撤']:>+9.1%}{r['持有年化']:>+9.1%}")
    print("-" * 96)
    print("注：年化波动率=日收益std×√244；持有年化=同窗口买入持有对照（非策略收益）；"
          "两个 ETF 用前复权价（512480 有两次份额拆分，raw 价有假暴跌）")

    # ---------- 图：假设"波动越大策略越好"是否成立 ----------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("bottom_reversal：标的波动率 vs 策略表现（参数不动横测）", fontsize=13)

    vols = [r["年化波动率"] * 100 for r in rows]
    anns = [r["策略年化"] * 100 for r in rows]
    bhs = [r["持有年化"] * 100 for r in rows]
    names = [r["标的"] for r in rows]

    # 左图：散点 x=波动率 y=策略年化，每个点标名字；灰叉=买入持有年化（对照）
    ax1.scatter(vols, anns, s=60, c="#d62728", zorder=3, label="策略年化")
    ax1.scatter(vols, bhs, s=60, marker="x", c="gray", zorder=3, label="买入持有年化（对照）")
    for x, y, n in zip(vols, anns, names):
        ax1.annotate(n, (x, y), textcoords="offset points", xytext=(6, 6), fontsize=9)
    ax1.axhline(0, color="black", lw=0.8)
    ax1.set_xlabel("标的年化波动率（%）")
    ax1.set_ylabel("年化收益（%）")
    ax1.set_title("假设检验：波动越大，策略年化是否越高？")
    ax1.legend()
    ax1.grid(alpha=0.3)

    # 右图：交易数柱状（样本量）+ 胜率标注——波动大信号是否更多、胜率是否更高
    x = np.arange(len(rows))
    ax2.bar(x, [r["交易数"] for r in rows], color="#1f77b4", alpha=0.85)
    for i, r in enumerate(rows):
        win_txt = f"胜率{r['胜率']:.0%}" if r["交易数"] else "无交易"
        ax2.text(i, r["交易数"] + 0.3, win_txt, ha="center", fontsize=9)
    ax2.set_xticks(x)
    ax2.set_xticklabels(names, rotation=30, ha="right", fontsize=9)
    ax2.set_ylabel("闭环交易数（笔）")
    ax2.set_title("样本量：波动越大，信号是否越多？")
    ax2.grid(alpha=0.3, axis="y")

    fig.tight_layout()
    out = "data/bottom_vol_fit.png"
    fig.savefig(out, dpi=130)
    print(f"\n✓ 图已存 {out}")


if __name__ == "__main__":
    main()
