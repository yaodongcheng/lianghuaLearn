# -*- coding: utf-8 -*-
"""拆解：bottom_reversal 从"年化 5.1%"到"年化 1.53%"的差额到底由什么造成（plans/20 追加）

起因：用户质疑——"我记得跑 bottom_reversal.py 时年化 5~6%，不可能转化一下就变 1.53%"。
质疑是对的：**一个改动只能解释一件事**，差 3.6 个百分点必须能逐项拆开，
拆不开就说明适配器有 bug。本脚本一次改一个变量，四步走到底：

    A 原版        engine.py    上证指数   2018-07 起   ← 策略文件 note 里的 5.1%
    B 换区间      engine.py    上证指数   2013-08 起   ← 只改起点
    C 换引擎口径  portfolio    上证指数   2013-08 起   ← 只改成交模型（T+1开盘→T+1收盘）
    D 换标的      portfolio    联接基金   2013-08 起   ← 只改标的，得到 run.py 里那行

跑法：python analysis/analyze_adapter_gap.py
"""
import sys

import pandas as pd

sys.path.insert(0, ".")
from quant import metrics                      # noqa: E402
from quant.adapter import strategy_as_portfolio  # noqa: E402
from quant.data import load_data               # noqa: E402
from quant.engine import run_backtest          # noqa: E402
from quant.portfolio import run_portfolio_backtest  # noqa: E402
from quant.portfolio_data import load_portfolio_navs  # noqa: E402
from quant.strategies import REGISTRY          # noqa: E402

ALIGN_START = "2013-08-22"      # 与 run.py 组合比选模式的统一起点一致（最晚就绪成分）
COST = 0.001
CASH = 10000.0


def row(name, eq, n_trades, unit="笔"):
    """统一口径算绩效（口径以 Knowledge/metrics.md 为准，全部走 quant/metrics.py）。

    ⚠ 两个引擎的"次数"不同义：engine 的 trades 是**一笔往返**（买+卖算 1），
    组合引擎的 log 是**成交日**（买一行、卖一行）→ 大致要除以 2 才可比。
    """
    return {"口径": name, "期末(元)": round(float(eq.iloc[-1]), 0),
            "年化": f"{metrics.annual_return(eq):+.2%}",
            "最大回撤": f"{metrics.max_drawdown(eq):.1%}",
            "成交次数": f"{n_trades} {unit}",
            "起点": str(eq.index[0].date()), "终点": str(eq.index[-1].date())}


def single(start):
    """单标的引擎（T+1 开盘成交，有指标预热段）跑上证指数。

    ⚠ load_data 默认只取近几年数据，不显式给 data_start 的话"换起点"会悄悄失效
    （首版就踩了：start 给 2013-08 但数据从 2018-01 开始，等于没换区间）。
    """
    strat = REGISTRY["bottom_reversal"]
    df, _ = load_data("上证指数", start="20120101")   # 早于回测起点 = 指标预热段
    trades, eq = run_backtest(df, strat.entry_fn, strat.exit.to_fn(),
                              start=start, cost=COST)
    return eq / eq.iloc[0] * CASH, len(trades)      # 归一成同样本金好对比


def portfolio(holdings, data_start, fund_mode):
    """组合引擎 + 适配器（T+1 收盘/净值成交，无预热段）。"""
    navs = load_portfolio_navs(holdings, data_start=data_start)
    eq, _w, log = run_portfolio_backtest(
        navs, strategy_as_portfolio("bottom_reversal", fund_mode=fund_mode),
        start=ALIGN_START, cost=COST, initial_cash=CASH)
    return eq, len(log) - 1                          # log 第一行是建仓，不算调仓


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    eq_a, n = single("2018-07-01")
    rows.append(row("A 原版：engine+上证指数+2018-07起", eq_a, n, "笔往返"))
    eq_b, n = single(ALIGN_START)
    rows.append(row("B 只换区间：engine+上证指数+2013-08起", eq_b, n, "笔往返"))
    eq, n = portfolio({"上证指数": "上证指数"}, "20130101", False)
    rows.append(row("C 再换引擎：portfolio+上证指数", eq, n, "个成交日"))
    eq, n = portfolio({"上证指数联接A": "fund:100053"}, "20110101", True)
    rows.append(row("D 再换标的：portfolio+联接基金（=run.py 那行）", eq, n, "个成交日"))

    print("\n" + "=" * 100)
    print("bottom_reversal 年化差额拆解（一步只改一个变量）")
    print("=" * 100)
    print(pd.DataFrame(rows).to_string(index=False))

    # —— 把 B 拆成两段：多出来的 2013~2018 究竟赚了还是亏了 ——
    seg = []
    for label, lo, hi in [("多出来的 2013-08~2018-07 段", ALIGN_START, "2018-07-01"),
                          ("原版覆盖的 2018-07~2026-07 段", "2018-07-01", "2026-12-31")]:
        s = eq_b.loc[lo:hi]
        seg.append({"分段": label, "起→终": f"{s.index[0].date()} → {s.index[-1].date()}",
                    "本段收益": f"{s.iloc[-1] / s.iloc[0] - 1:+.1%}",
                    "本段年化": f"{metrics.annual_return(s):+.2%}",
                    "本段回撤": f"{metrics.max_drawdown(s):.1%}"})
    print("\n【把 B 那条净值切两段看】同一条回测曲线，前后两段完全不是一个策略的样子：")
    print(pd.DataFrame(seg).to_string(index=False))
