# -*- coding: utf-8 -*-
"""
quant/plot_attribution.py — ⑤ 归因图零件：各成分累计贡献曲线

单独一个文件，是因为它回答的问题和净值/权重图不一样：
    净值图  = 组合总共赚了多少
    权重图  = 钱放在哪
    **本图** = 钱是从哪条腿赚回来的（动态持仓下这三件事经常错位）
"""

from quant.attribution import cum_contrib, daily_contrib

__all__ = ["panel_cum_contrib"]


def panel_cum_contrib(ax, eq, weights, log, mark_dates=None):
    """把"各成分累计贡献（元）"画到给定的坐标轴上（供组合图当一联用）。

    用金额而不是收益率：动态持仓下每条腿的仓位一直在变，收益率没有共同分母、
    不能相加；金额可以相加，且黑色"合计"线必须与组合总盈亏重合（图上自带对账）。
    """
    try:
        cum = cum_contrib(daily_contrib(eq, weights, log))
    except (ValueError, AssertionError) as e:      # 归因失败不该让整张图画不出来
        ax.text(0.5, 0.5, f"归因不可用：{type(e).__name__}", ha="center",
                transform=ax.transAxes, fontsize=9, color="0.4")
        ax.grid(alpha=0.3)
        return None

    total_pnl = eq.iloc[-1] - eq.iloc[0]
    share = lambda v: f"（{v / total_pnl:.0%}）" if abs(total_pnl) > 1 else ""
    for n in cum.attrs["names"]:       # 颜色循环与权重图一致，方便上下对照
        v = cum[n].iloc[-1]
        ax.plot(cum.index, cum[n], lw=1.3, label=f"{n} {v:+,.0f}元{share(v)}")
    ax.plot(cum.index, cum["成本"], color="0.5", lw=1.0, ls=":",
            label=f"交易成本 {cum['成本'].iloc[-1]:+,.0f}元")
    ax.plot(cum.index, cum["合计"], color="black", lw=1.6, alpha=0.8,
            label=f"合计 {cum['合计'].iloc[-1]:+,.0f}元（=组合总盈亏，对账用）")
    ax.axhline(0, color="0.4", lw=0.8)
    for d in (mark_dates if mark_dates is not None else []):
        ax.axvline(d, color="purple", alpha=0.12, lw=0.8)
    ax.set_title("各成分累计贡献（元；Σ 昨日份数 × 今日净值变化）"
                 "——与上图对照：仓位大 ≠ 贡献大", fontsize=10, loc="left")
    ax.legend(ncol=3, fontsize=8.5)
    ax.grid(alpha=0.3)
    return cum
