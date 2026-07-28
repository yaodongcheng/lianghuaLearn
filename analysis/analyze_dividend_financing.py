# -*- coding: utf-8 -*-
"""
analysis/analyze_dividend_financing.py — 计划 16：知乎"分红融资比"选股策略回测

策略原文（Knowledge/zhihu/分红融资比策略.md，作者 kaer）：
- 金标准：历史累计分红 > 历史累计融资（分红融资比 > 1）才值得投资
- 全 A 约 800 只通过；声称这批股票组成的指数长期跑赢沪深300/中证500 且回撤更小
- 辅以：上市满 8 年、分红比例 30~70%、行业/股息率优选（主观部分本回测不模拟）

本脚本的机械化规则（把"金标准"翻译成可执行、无未来函数的版本）：
1. 选股日 T0：只用 除权除息日 ≤ T0 的现金分红、发生日 ≤ T0 的融资事件
   （"已公告未除息"不算——那是偷看未来）
2. 过滤：上市满 8 年 + 累计融资 > 0 + 分红融资比 > 1
3. 排序取 top 20 等权，T0 次日收盘买入并持有至今，10000 元起
4. 基准：沪深300 / 中证500 / 中证红利（红利类策略的天然对照）

数据缺口与对策（必须披露，见报告）：
- IPO/增发表只覆盖 2010 年起 → 老股融资被低估、比率被高估
- 对策：先用可得数据粗筛 top 40，对其中 2010 年前上市的逐股补全 IPO
  （stock_ipo_summary_cninfo 逐股接口），重算比率后再定 top 20
- 幸存者偏差：只能回测"至今未退市"的股票（退市股无价格数据）

运行：python analysis/analyze_dividend_financing.py
产出：终端报告 + data/dividend_financing_result.png
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fetch_data import (DATA_DIR, DIVFIN_DIR, fetch_dividend_table,
                        fetch_financing_tables, fetch_ipo_amount)
from quant.data import load_data
from quant.portfolio import run_portfolio_backtest
from quant.rebalance import buy_and_hold
from quant.report_portfolio_parts import load_bench, perf_row

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

COST = 0.001
INITIAL = 10000.0
TOP_N = 20
DIV_AUDIT_FLOOR = 10e8   # 老股 IPO 补全的分红门槛：10 亿
YEARS_LISTED_MIN = 8  # 原文：上市满 8 年


def build_dividend_panel():
    """拉全部报告期分红表 → 每股明细长表 (code, name, amount, ex_date)。
    amount = 每10股派息/10 × 总股本 = 该次现金分红总额（元）。"""
    cache = DIVFIN_DIR / "dividend_panel.csv"
    if cache.exists():
        print("✓ 使用缓存 dividend_panel.csv")
        return pd.read_csv(cache, parse_dates=["ex_date"], dtype={"code": str})
    frames = []
    periods = ([f"{y}1231" for y in range(2000, 2026)]
               + [f"{y}0630" for y in range(2000, 2026)])
    for i, p in enumerate(periods):
        try:
            t = fetch_dividend_table(p)
            frames.append(t)
            print(f"  [{i + 1}/{len(periods)}] {p}: {len(t)} 只")
            time.sleep(0.5)  # 礼貌限速，网页接口别打太猛
        except Exception as e:
            print(f"  [{i + 1}/{len(periods)}] {p} 失败（跳过）: {type(e).__name__} "
                  f"{str(e)[:60]}")
    panel = pd.concat(frames, ignore_index=True)
    panel["amount"] = panel["div_per_10"] / 10 * panel["total_shares"]
    panel = panel.dropna(subset=["ex_date"])  # 无除息日 = 未实施，不算已回馈
    panel.to_csv(cache, index=False)
    print(f"✓ 分红明细面板：{len(panel)} 行（存 dividend_panel.csv）")
    return panel[["code", "name", "amount", "ex_date"]]


def audit_ipo(codes, as_of):
    """老股 IPO 补全：取数走 fetch_data 的轮子（缓存+重试+显式失败都在轮子里）。

    这层薄包装只为了保留脚本内的调用名，逻辑与踩坑记录见 fetch_data.fetch_ipo_amount。
    """
    return fetch_ipo_amount(codes, as_of=as_of)


def select_stocks(as_of, verbose=True):
    """point-in-time 选股：返回 (入选 top N 表, 全体通过数, IPO 补全只数)。

    数据完整性分三层（重要，决定结果可信度）：
    - 2010 年后上市：IPO/增发/配股三表齐全 → 比率直接可信
    - 2010 年前上市：缺 IPO 与 2010 年前增发 → 对累计分红 ≥ DIV_AUDIT_FLOOR 的
      逐股补全 IPO（per-stock 接口），否则它们的比率全是错的（茅台 IPO 后再没
      融过资，三表里融资=0，不补 IPO 它会被"融资>0"过滤器误杀）
    - 残余缺口：2010 年前的增发仍缺（配股表 1991 年起覆盖），披露
    """
    as_of = pd.Timestamp(as_of)
    div = build_dividend_panel()
    fin = fetch_financing_tables()

    # —— 只用 T0 及以前已落地的数据（本策略的防未来函数核心）——
    div_t0 = div[div["ex_date"] <= as_of]
    fin_t0 = fin[fin["date"] <= as_of]

    agg_div = div_t0.groupby("code")["amount"].sum()
    agg_fin = fin_t0.groupby("code")["amount"].sum()
    names = div_t0.groupby("code")["name"].last()
    list_dt = (fin_t0[fin_t0["kind"] == "ipo"]
               .groupby("code")["list_date"].min())  # NaT = 2010 年前上市

    df = pd.DataFrame({"name": names, "div": agg_div})
    df["fin"] = agg_fin.reindex(df.index).fillna(0.0)
    df["list_date"] = list_dt.reindex(df.index)
    cutoff = as_of - pd.DateOffset(years=YEARS_LISTED_MIN)
    df["old_enough"] = df["list_date"].isna() | (df["list_date"] <= cutoff)
    # 上市满 8 年判定：IPO 表查不到 = 2010 年前上市，回看必然满 8 年
    df = df[df["old_enough"] & (df["div"] > 0)]

    # —— 老股 IPO 补全：只补"分红大户"（它们才可能进 top N），控制调用量 ——
    need_audit = df[(df["list_date"].isna())
                    & (df["div"] >= DIV_AUDIT_FLOOR)].index.tolist()
    n_fixed = 0
    if need_audit:
        print(f"2010 年前上市且累计分红 ≥ {DIV_AUDIT_FLOOR / 1e8:.0f} 亿的 "
              f"{len(need_audit)} 只，逐股补全 IPO 募资…")
        ipo_fix, ipo_failed = audit_ipo(need_audit, as_of)
        for code, amt in ipo_fix.items():
            if amt > 0:
                df.loc[code, "fin"] += amt
                n_fixed += 1
        print(f"IPO 补全完成：{n_fixed}/{len(need_audit)} 只募资额上调")
        if ipo_failed:
            # 补全失败的股票比率不可信（可能严重虚高），从排名剔除——宁缺毋假
            print(f"⚠ {len(ipo_failed)} 只补全失败，从排名剔除：{ipo_failed}")
            df = df.drop(index=[c for c in ipo_failed if c in df.index])

    df = df[df["fin"] > 0]
    df["ratio"] = df["div"] / df["fin"]
    passed = df[df["ratio"] > 1].sort_values("ratio", ascending=False)
    if verbose:
        print(f"\n截至 {as_of:%Y-%m-%d}：上市满8年且有分红记录 {len(df)} 只，"
              f"分红融资比 > 1 的 {len(passed)} 只")
    return passed.head(TOP_N), len(passed), n_fixed


def backtest(picks, as_of):
    """top N 等权、T0 次日收盘买入持有（不再平衡），对照三基准。

    为什么用 hfq 不用项目默认的 qfq（2026-07-27 实测踩坑）：
    前复权是"以今天为基准向前【减】调整额"，巨额分红股的历史价会被减成负数
    （兖矿能源 2021-01 的 qfq 价 = -1.01 元）→ 负价买入 = 负份额，组合账目直接
    爆炸（回撤 -124.6% 这种数学上不可能的数就是这么来的）。
    后复权是"以上市日为基准向未来【乘】"，价格恒正，且语义就是"分红再投资"，
    才是长期持有回测的正确口径。收益率口径下 hfq 与 qfq 理论等价，只是不会负。
    """
    as_of = pd.Timestamp(as_of)
    start_trade = as_of + pd.Timedelta(days=1)
    nav = {}
    failed = []
    for code, row in picks.iterrows():
        try:
            df, _ = load_data(f"stock:{code}", start=str(start_trade.date()),
                              adjust="hfq")
            nav[row["name"]] = df[["close"]]
        except Exception as e:
            failed.append((code, row["name"], str(e)[:60]))
            print(f"✗ {row['name']}({code}) 取数失败，剔除：{str(e)[:60]}")
    if failed:
        picks = picks.drop(index=[c for c, _, _ in failed])
    w = {n: 1 / len(nav) for n in nav}
    # 等权买入、持有至今 → 决策函数用 buy_and_hold（组合引擎的契约见 quant/rebalance.py）
    eq, weights, _ = run_portfolio_backtest(nav, buy_and_hold(w), cost=COST,
                                            initial_cash=INITIAL)

    benches = {}
    for bname in ("沪深300", "中证500"):
        # 基准对齐/缩放/取数失败处理走框架的 load_bench（口径与组合报告一致）
        bs = load_bench(bname, eq)
        if bs is not None:
            benches[bname] = bs
    # 中证红利(000922)本是最贴切的对照，但新浪该指数数据只到 2019-01（2026-07-27
    # 实测），取不到回测区间，跳过——宁缺毋假
    return eq, weights, benches, nav


def report_and_plot(as_of, picks, n_passed, n_fixed, eq, weights, benches, nav):
    print(f"\n{'=' * 74}\n策略① 分红融资比选股（T0={as_of} 选股，次日收盘买入，持有至今）")
    print(f"入选 {len(picks)} 只（全市场通过比率>1 共 {n_passed} 只，"
          f"IPO 补全上调 {n_fixed} 只）：")
    show = picks[["name", "div", "fin", "ratio"]].copy()
    show["div"] = (show["div"] / 1e8).round(1)
    show["fin"] = (show["fin"] / 1e8).round(1)
    show["ratio"] = show["ratio"].round(2)
    show.columns = ["名称", "累计分红(亿)", "累计融资(亿)", "分红融资比"]
    print(show.to_string())

    # 绩效行统一用框架的 perf_row（口径单一来源，见 Knowledge/metrics.md）
    rows = [perf_row(eq, f"分红融资比top{len(picks)}", INITIAL)]
    for bn, bs in benches.items():
        rows.append(perf_row(bs, bn, INITIAL))       # load_bench 已缩放到同一起点金额
    print(f"\n区间：{eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}"
          f"（{(eq.index[-1] - eq.index[0]).days / 365.25:.1f} 年）  初始 {INITIAL:.0f} 元")
    print(pd.DataFrame(rows).set_index("口径").to_string())

    fig, ax = plt.subplots(figsize=(13, 6))
    ax.plot(eq.index, eq / eq.iloc[0], color="red", lw=2,
            label=f"分红融资比top{len(picks)}组合")
    for bn, bs in benches.items():
        ax.plot(bs.index, bs / bs.iloc[0], lw=1.2, alpha=0.8, label=bn)
    ax.set_title(f"策略① 分红融资比选股：T0={as_of} 等权买入持有（净值归一化）")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = DATA_DIR / f"dividend_financing_{str(as_of)[:10]}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"✓ 图已存 {out}")
    return pd.DataFrame(rows).set_index("口径")


if __name__ == "__main__":
    # 选股日扰动（防过拟合自检的硬项）：两个相隔 2 年的 T0，名单高度重叠 +
    # 结论方向一致，才说明策略不是靠"恰好选在某天"吃饭的
    summary = {}
    for T0 in ("2019-01-02", "2021-01-04"):
        picks, n_passed, n_fixed = select_stocks(T0)
        eq, weights, benches, nav = backtest(picks, T0)
        tbl = report_and_plot(T0, picks, n_passed, n_fixed, eq, weights, benches, nav)
        summary[T0] = tbl.loc[tbl.index[0]]
    print(f"\n{'=' * 74}\n选股日扰动汇总（top20 组合）：")
    print(pd.DataFrame(summary).to_string())
