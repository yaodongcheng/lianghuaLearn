# -*- coding: utf-8 -*-
"""analysis/analyze_trend_fit.py — plans/15：趋势型行业基金用什么策略（策略性格 × 标的人格匹配矩阵）

问题来源（2026-07-27 用户提问，plans/14 的后续）：抄底策略（bottom_reversal）在
趋势型标的上失效（盈亏比崩到 ~1.0），那趋势型行业基金该用什么策略？

矩阵设计：
- 标的按"性格"分组：震荡型（上证/证券ETF，均值回复，对照组）
  vs 趋势型（创业板指/科创50/半导体ETF）
- 策略也按性格选：抄底（均值回复，plans/14 已知）/ 牛熊混合（plans/12）/
  年线过滤（本次新建，趋势跟踪教科书版）/ MACD（高频趋势，对照）
- 买入持有是门槛：plans/12/13 的共同教训是趋势型品种"拿着不动"很难被打败，
  趋势策略的合理目标是【收益打折不多 + 回撤大幅压缩】（夏普/卡玛视角），
  不是收益超过持有

方法纪律（与 plans/14 相同）：参数全部原样不动，不调参。
DATA_START 多取 2.5 年：MA250 预热需要真实历史数据，否则策略在回测起点
"失明"半年（预热期干等）——预热用真实数据比用"回测起点之后的数据"更公平。

用法：python analysis/analyze_trend_fit.py
产出：终端矩阵表 + data/trend_fit_matrix.png + 真实场外基金（007301）验证块
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
from quant.exits import adjust_for_fund
from quant.strategies import REGISTRY

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

START = "2018-07-01"     # 与 run.py / plans/14 同口径
DATA_START = "20160101"  # MA250 预热缓冲（指数实际历史更早，ETF/基金从上市日起）
COST = 0.001             # 双边各 0.1%

# 标的按"性格"排序：震荡型（均值回复，对照组）→ 趋势型
INSTRUMENTS = [
    ("上证指数", None, "震荡"),
    ("512880", "qfq", "震荡·高波"),
    ("创业板指", None, "趋势"),
    ("科创50", None, "趋势"),
    ("512480", "qfq", "趋势·行业"),
]
STRATEGIES = ["bottom_reversal", "bull_bear_hybrid", "trend_ma250", "macd_cross"]
LABEL = {"买入持有": "买入持有", "bottom_reversal": "底部反包\n(均值回复)",
         "bull_bear_hybrid": "牛熊混合", "trend_ma250": "年线过滤\n(趋势)",
         "macd_cross": "MACD趋势\n(高频)"}
FUND = "fund:007301"     # 国联安中证半导体ETF联接C：512480 的场外联接基金（支付宝可买）；
                         # 007301 与深市股票代码段撞码，用 fund: 前缀强制按基金解析


def bench_stats(bt):
    """买入持有参考行：净值 = 收盘价归一，复用 metrics 口径（CLAUDE.md 规则 3）。"""
    eq = bt["close"] / bt["close"].iloc[0]
    return {"年化": metrics.annual_return(eq), "回撤": metrics.max_drawdown(eq),
            "夏普": metrics.sharpe_ratio(eq), "卡玛": metrics.calmar_ratio(eq),
            "交易数": None, "年均交易": None}


def strategy_stats(df, bt, strategy_name, kind):
    """跑一个策略，返回与 bench_stats 同口径的指标行。"""
    st = REGISTRY[strategy_name]
    exit_rule = adjust_for_fund(st.exit, kind)     # 基金模式自动加 min_hold（ExitSpec 类）
    exit_fn = exit_rule.to_fn() if hasattr(exit_rule, "to_fn") else exit_rule
    trades, eq, _ = run_backtest_ex(df, st.entry_fn, exit_fn, start=START, cost=COST)
    s = metrics.summarize(trades, eq)
    years = len(bt) / 244
    return {"年化": s["年化"], "回撤": s["最大回撤"], "夏普": s["夏普"], "卡玛": s["卡玛"],
            "交易数": s["交易数"], "年均交易": s["交易数"] / years if years > 0 else None}


def run_instrument(target, adjust, personality):
    """一个标的：买入持有 + 4 个策略全跑一遍。返回 (行字典, 实际区间, 显示名)。"""
    df, info = load_data(target, start=DATA_START, adjust=adjust)
    bt = df.loc[pd.Timestamp(START):]
    rows = {"买入持有": bench_stats(bt)}
    for name in STRATEGIES:
        rows[name] = strategy_stats(df, bt, name, info["kind"])
    span = f"{bt.index[0]:%Y-%m-%d}~{bt.index[-1]:%Y-%m-%d}"
    label = f"{info['name']}({personality})"
    return rows, span, label


def print_block(label, span, rows):
    """单标的对比块：买入持有在首行（门槛），策略按年化和夏普都能一眼比。"""
    print(f"\n—— {label}  区间 {span} ——")
    print(f"{'策略':<18}{'年化':>8}{'最大回撤':>9}{'夏普':>7}{'卡玛':>7}{'交易数':>7}{'年均交易':>9}")
    for name in ["买入持有"] + STRATEGIES:
        r = rows[name]
        n = f"{r['交易数']}" if r["交易数"] is not None else "—"
        f = f"{r['年均交易']:.1f}" if r["年均交易"] is not None else "—"
        print(f"{LABEL[name].replace(chr(10), ''):<18}{r['年化']:>+8.1%}{r['回撤']:>+9.1%}"
              f"{r['夏普']:>7.2f}{r['卡玛']:>7.2f}{n:>7}{f:>9}")


def plot_matrix(all_rows, inst_labels, out):
    """热力图：行=标的（震荡→趋势），列=买入持有+策略。三张：年化/回撤/夏普。
    一眼看"策略性格 × 标的性格"的匹配格局（右下角 vs 左上角该有反差）。"""
    cols = ["买入持有"] + STRATEGIES
    keys = [("年化", "年化收益", "{:+.0%}"), ("回撤", "最大回撤", "{:.0%}"), ("夏普", "夏普比率", "{:.2f}")]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    fig.suptitle("策略性格 × 标的性格 匹配矩阵（参数不动；2018-07 起，部分标的从上市日起）", fontsize=13)
    for ax, (key, title, fmt) in zip(axes, keys):
        mat = np.array([[all_rows[il][c][key] for c in cols] for il in inst_labels], dtype=float)
        v = np.nanmax(np.abs(mat))
        im = ax.imshow(mat, cmap="RdYlGn", vmin=-v, vmax=v, aspect="auto")
        for i in range(len(inst_labels)):
            for j in range(len(cols)):
                ax.text(j, i, fmt.format(mat[i, j]), ha="center", va="center", fontsize=9)
        ax.set_xticks(range(len(cols)))
        ax.set_xticklabels([LABEL[c] for c in cols], fontsize=9)
        ax.set_yticks(range(len(inst_labels)))
        ax.set_yticklabels(inst_labels, fontsize=9)
        ax.set_title(title)
        fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"\n✓ 图已存 {out}")


def main():
    # ---------- ① 5 个指数/ETF 的矩阵 ----------
    all_rows, inst_labels = {}, []
    for target, adjust, personality in INSTRUMENTS:
        rows, span, label = run_instrument(target, adjust, personality)
        print_block(label, span, rows)
        all_rows[label] = rows
        inst_labels.append(label)
    plot_matrix(all_rows, inst_labels, "data/trend_fit_matrix.png")

    # ---------- ② 真实场外基金验证：007301（512480 的联接基金，净值模式） ----------
    print(f"\n{'=' * 74}\n真实场外基金验证：{FUND}（国联安中证半导体ETF联接C，"
          f"T+1 净值成交，与 512480 场内版对照）\n{'=' * 74}")
    rows, span, label = run_instrument(FUND, None, "趋势·行业")
    print_block(label, span, rows)
    print("※ 基金口径提示：C类无申购费，销售服务费（约0.4%/年）未计入——它同时拖累"
          "持有和策略（策略空仓期不付），此处成本口径双边 0.1% 偏乐观但横向可比")


if __name__ == "__main__":
    main()
