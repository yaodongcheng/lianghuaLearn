# -*- coding: utf-8 -*-
"""
quant/attribution.py — ⑤ 评估层：组合收益归因的**计算**（打印在 report_attribution.py）

为什么需要它（新手最容易犯的错）：
    看到"纳指同期涨了 300%"就以为组合的收益主要来自纳指——**不对**。原因有两个：
    ① 每条腿只占 25% 仓位；② 再平衡会**主动把涨多的减掉**（仓位一直被压回 25%）。
    真正的贡献取决于"每一天你手上实际拿着多少份"，不是这只基金自己涨了多少。

因此归因用【金额法】，直接对引擎逐日记的账做拆分：

    某成分某日损益(元) = 昨日收盘份数 × (今日净值 − 昨日净值)

- 成交按当日净值成交 → 买卖本身不产生盈亏，只产生成本（所以成本单独一列，
  不摊到成分头上——摊法有主观性）
- 现金不生息 → 现金的贡献恒为 0。**这不是"没信息"，这就是机会成本的样子**
- 守恒式（daily_contrib 里用 assert 把关，不靠自觉）：
      Σ 各成分当日损益 − 当日成本 = 当日组合总资产变化

⚠️ 口径：归因是**算术加总（元）**。各成分贡献的元数相加等于总盈亏；但"贡献百分比"
不能相加等于总收益率（分母不同）。想看百分比就除以**本金**，别除以期末金额。
"""

import numpy as np
import pandas as pd

__all__ = ["daily_contrib", "cum_contrib", "summary_table", "attribute_by_periods"]


def daily_contrib(eq, weights, log, check=True):
    """日度损益矩阵：各成分持有损益 + 成本，与引擎账目严格对账。

    参数：
        eq, weights, log: run_portfolio_backtest 的三个返回值原样传进来
                          （份数/现金/净值/分腿损益挂在 weights.attrs 里，由引擎附带）
        check: 是否做守恒断言（默认开；关掉只在调试时用）

    返回 DataFrame：索引=交易日，列=各成分损益(元) + "成本"(元，正数=花掉的钱)
    """
    for k in ("shares", "cash", "prices"):
        if k not in weights.attrs:
            raise ValueError(f"weights.attrs 里没有 {k!r}：请用当前版本的 "
                             f"quant/portfolio.py 重跑回测（归因需要引擎附带的份数）")
    shares, px = weights.attrs["shares"], weights.attrs["prices"]
    names = list(shares.columns)

    # 昨日份数 × 今日净值变化 = 今日持有损益（第一天没有"昨日"→ 0）
    rebuilt = shares.shift(1).fillna(0.0) * px.diff().fillna(0.0)
    # 引擎自己逐日记的账优先用；同时和上面的反推互相印证——两者对不上说明引擎的
    # 份数记录与损益记录不自洽（改引擎时最容易出的错），直接报错。
    pnl = weights.attrs.get("pnl")
    if pnl is None:
        pnl = rebuilt
    elif check:
        gap = float((pnl - rebuilt).abs().max().max())
        assert gap < 1e-6, f"引擎分腿损益与份数反推不一致：最大差 {gap:.6f} 元"

    fee = pd.Series(0.0, index=eq.index)
    if len(log):
        for _, r in log.iterrows():
            fee.loc[r["日期"]] = r["成本"]
    out = pnl.copy()
    out["成本"] = fee

    if check:
        # 守恒：Σ成分损益 − 成本 = 总资产变化。对不上说明归因口径与引擎不一致，
        # 这种情况下归因表会"看起来合理但其实错了"，所以宁可直接报错。
        resid = float(np.abs((pnl.sum(axis=1) - fee) - eq.diff().fillna(0.0)).max())
        scale = max(float(eq.max()), 1.0)
        assert resid / scale < 1e-9, (
            f"归因账目对不上引擎：最大残差 {resid:.6f} 元（相对 {resid / scale:.2e}）")
    out.attrs["names"] = names
    return out


def cum_contrib(contrib):
    """累计贡献曲线（画图用）：各成分累计损益(元) + "成本"取负 + "合计"。

    为什么用累计金额画图而不是累计收益率：动态持仓的组合里每条腿的仓位一直在变，
    收益率没有共同分母、不能相加；金额可以，且 Σ各腿 − 成本 == 组合总盈亏（可核对）。
    """
    names = contrib.attrs.get("names") or [c for c in contrib.columns if c != "成本"]
    out = contrib[names].cumsum()
    out["成本"] = -contrib["成本"].cumsum()        # 成本画成负贡献，和各腿同向可读
    out["合计"] = out[names].sum(axis=1) + out["成本"]
    out.attrs["names"] = names
    return out


def summary_table(eq, weights, log, initial, contrib=None):
    """全区间总账表（报告和图共用同一份数字，避免两处口径不一致）。

    返回 (DataFrame, contrib)：表的行=各成分 + 交易成本 + 现金，
    列=贡献(元)/占总盈亏/占本金/平均仓位/自身涨幅
    """
    contrib = daily_contrib(eq, weights, log) if contrib is None else contrib
    names = contrib.attrs["names"]
    total_pnl = eq.iloc[-1] - initial
    px = weights.attrs["prices"]
    pct = lambda v: f"{v / total_pnl:.1%}" if abs(total_pnl) > 1e-9 else "—"

    rows = []
    for n in names:
        v = contrib[n].sum()
        rows.append({"成分": n, "贡献(元)": round(v, 0), "占总盈亏": pct(v),
                     "占本金": f"{v / initial:+.1%}",
                     "平均仓位": f"{weights[n].mean():.1%}",
                     "自身涨幅": f"{px[n].iloc[-1] / px[n].iloc[0] - 1:+.1%}"})
    fee_total = contrib["成本"].sum()
    rows.append({"成分": "交易成本", "贡献(元)": round(-fee_total, 0),
                 "占总盈亏": pct(-fee_total), "占本金": f"{-fee_total / initial:+.1%}",
                 "平均仓位": "—", "自身涨幅": "—"})
    cash_w = 1 - weights[names].sum(axis=1)
    rows.append({"成分": "现金(不生息)", "贡献(元)": 0.0, "占总盈亏": "0.0%",
                 "占本金": "+0.0%", "平均仓位": f"{cash_w.mean():.1%}", "自身涨幅": "—"})
    return pd.DataFrame(rows).set_index("成分"), contrib


def attribute_by_periods(contrib, eq, bounds):
    """按区间汇总归因：每段起止 + 各成分贡献(元) + 成本 + 该段组合收益率。

    bounds: 区间切点日期列表（如每次再平衡日、或每年第一个交易日）。
            每段含左端、不含右端，最后一段到数据末尾。
    """
    idx = contrib.index
    cuts = [pd.Timestamp(b) for b in bounds if pd.Timestamp(b) in idx]
    if not cuts or cuts[0] != idx[0]:
        cuts = [idx[0]] + cuts
    rows = []
    for j, s in enumerate(cuts):
        e = cuts[j + 1] if j + 1 < len(cuts) else None
        # 损益按"这段区间内发生的每日损益"加总；区间左端那天的损益属于上一段
        # （它是"昨收到今收"的变化），所以从 s 的下一天算起
        seg = contrib.loc[contrib.index > s] if e is None \
            else contrib.loc[(contrib.index > s) & (contrib.index <= e)]
        if not len(seg):
            continue
        end_day = seg.index[-1]
        row = {"起": s, "止": end_day}
        row.update({c: seg[c].sum() for c in contrib.columns})
        row["段收益率"] = eq.loc[end_day] / eq.loc[s] - 1
        row["期末金额"] = eq.loc[end_day]
        rows.append(row)
    return pd.DataFrame(rows)
