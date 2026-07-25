# -*- coding: utf-8 -*-
"""
quant/metrics.py — ⑤ 评估层：绩效指标计算（口径以 Knowledge/metrics.md 为准）

口径说明（重要）：
- 年化收益用【日历年化 CAGR】= (期末/期初)^(365.25/自然天数) − 1。
  metrics.md 里的 (252/交易天数) 是等价近似；本项目统一日历年化，原因：
  ①与 v1~v4 全部历史报告可比（它们用这个口径）；②不依赖"一年几个交易日"的假设。
- 波动率/夏普仍按交易日口径（日收益率 std × √252），这是行业惯例，两者不冲突。
- 净值曲线约定：空仓期净值=现金（不增长），年化按全区间计算（含空仓时间）。
"""

import numpy as np


def annual_return(eq):
    """年化收益率（CAGR，日历年化）。eq：净值 Series（date 索引，期初≈1）。"""
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1
    return (1 + total) ** (1 / n_years) - 1 if total > -1 else -1


def max_drawdown(eq):
    """最大回撤 = min(净值 / 历史最高净值 − 1)。从最高点最多亏过多少（负数）。"""
    return (eq / eq.cummax() - 1).min()


def volatility(eq):
    """年化波动率 = 日收益率 std × √252。"""
    return eq.pct_change().std() * np.sqrt(252)


def sharpe_ratio(eq, rf=0.03):
    """夏普 = (年化 − 无风险利率) / 年化波动率。rf 默认 3%（约国债/货基水平）。"""
    vol = volatility(eq)
    return (annual_return(eq) - rf) / vol if vol > 0 else float("nan")


def calmar_ratio(eq):
    """卡玛 = 年化 / |最大回撤|。回撤为 0（没交易过）时无意义，返回 nan。"""
    mdd = max_drawdown(eq)
    return annual_return(eq) / abs(mdd) if mdd < 0 else float("nan")


def trade_stats(trades):
    """交易统计：笔数 / 胜率 / 平均每笔 / 平均盈 / 平均亏 / 盈亏比。
    注意：胜率高 ≠ 赚钱，要和盈亏比一起看（metrics.md 第 4 节）。"""
    n = len(trades)
    if n == 0:
        return {"交易数": 0, "胜率": float("nan"), "平均每笔": float("nan"),
                "平均盈": float("nan"), "平均亏": float("nan"), "盈亏比": float("nan")}
    r = trades["收益率"]
    wins, losses = r[r > 0], r[r <= 0]
    avg_win = wins.mean() if len(wins) else float("nan")
    avg_loss = losses.mean() if len(losses) else float("nan")
    pl = abs(avg_win / avg_loss) if len(wins) and len(losses) and avg_loss != 0 else float("nan")
    return {"交易数": n, "胜率": (r > 0).mean(), "平均每笔": r.mean(),
            "平均盈": avg_win, "平均亏": avg_loss, "盈亏比": pl}


def summarize(trades, eq):
    """一表汇总：交易统计 + 年化/回撤/夏普/卡玛（报告层直接取用）。"""
    s = trade_stats(trades)
    s.update({"年化": annual_return(eq), "最大回撤": max_drawdown(eq),
              "夏普": sharpe_ratio(eq), "卡玛": calmar_ratio(eq),
              "总收益": eq.iloc[-1] / eq.iloc[0] - 1})
    return s
