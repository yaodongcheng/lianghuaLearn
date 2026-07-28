# -*- coding: utf-8 -*-
"""
quant/report_attribution.py — ⑤ 归因的**打印**（算法在 attribution.py）

两个入口，按用途分：
    print_contrib      一小块总账表 → 每次组合回测都打（report_portfolio 固定内容之一）
    print_attribution  总账 + 分段表 → 想看"每年 / 每次调仓之间谁在出力"时打
                       （analysis/analyze_portfolio_attribution.py 用）
"""

from quant.attribution import attribute_by_periods, summary_table

__all__ = ["print_contrib", "print_attribution"]

_READ = ("读法：'贡献(元)' 可以直接相加 = 总盈亏；和 '自身涨幅' 差得远，"
         "说明仓位与再平衡改变了这条腿的实际作用。")


def print_contrib(name, eq, weights, log, initial):
    """收益归因总账：这些钱到底是哪条腿赚的（口径见 quant/attribution.py）。

    为什么每次组合回测都打印它：组合是**动态持仓**（权重漂移 + 再平衡削减），
    "某只基金涨得最多"和"某只基金给我赚得最多"经常不是同一只。只看净值曲线
    看不出这个差别，也就看不出再平衡到底动了谁。
    """
    try:
        tbl, _contrib = summary_table(eq, weights, log, initial)
    except (ValueError, AssertionError) as e:         # 归因不该让整个实验失败
        print(f"⚠ 收益归因跳过（{type(e).__name__}: {e}）")
        return None
    print("\n收益归因（金额法：某腿贡献 = Σ 昨日份数 × 今日净值变化，元）：")
    print(tbl.to_string())
    print(_READ)
    print(f"想看分段（每年 / 每次调仓）：python analysis/analyze_portfolio_attribution.py "
          f"{name} rebalance")
    return tbl


def print_attribution(name, eq, weights, log, initial, by="Y", max_rows=80):
    """总账 + 分段表。by="Y" 按年份切（可读）；"rebalance" 按每次再平衡切。"""
    tbl0, contrib = summary_table(eq, weights, log, initial)
    names = contrib.attrs["names"]
    total_pnl = eq.iloc[-1] - initial

    print(f"\n{'=' * 78}\n收益归因：{name}（金额法，单位：元）\n{'=' * 78}")
    print(f"区间 {eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}   "
          f"本金 {initial:.0f} → 期末 {eq.iloc[-1]:.0f}   总盈亏 {total_pnl:+.0f} 元")
    print(f"\n【全区间总账】\n{tbl0.to_string()}")
    print(_READ)

    if by == "rebalance" and len(log) > 1:
        bounds, label = list(log["日期"]), "每次再平衡之间"
    else:
        bounds = [g.index[0] for _, g in eq.groupby(eq.index.year)]
        label = "按年份"
    tbl = attribute_by_periods(contrib, eq, bounds)
    if len(tbl) > max_rows:
        print(f"\n【分段归因·{label}】共 {len(tbl)} 段，只显示前 {max_rows} 段"
              f"（想看全部：调 max_rows 或换 by='Y'）")
        tbl = tbl.head(max_rows)
    else:
        print(f"\n【分段归因·{label}】共 {len(tbl)} 段")
    show = tbl.copy()
    show["起"] = show["起"].dt.strftime("%Y-%m-%d")
    show["止"] = show["止"].dt.strftime("%Y-%m-%d")
    for c in names + ["成本", "期末金额"]:
        show[c] = show[c].round(0)
    show["段收益率"] = show["段收益率"].map(lambda v: f"{v:+.1%}")
    print(show.to_string(index=False))
    return contrib, tbl
