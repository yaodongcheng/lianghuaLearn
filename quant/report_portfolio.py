# -*- coding: utf-8 -*-
"""
quant/report_portfolio.py — ⑤ 评估层（组合版）：从组合回测产出到人能看的报告

与 report.py（单标的）的对应关系：
    report.run_experiment                      单标的：标的 × 择时策略 → 报告
    report_portfolio.run_portfolio_experiment  组合：  配方 × 决策函数 → 报告

组合报告固定包含四样东西（每一样都是防自欺的机制，不是装饰）：
1. **对照组**：同一批成分、同样权重，但建仓后永不调仓 → 再平衡到底值多少钱
2. **基准**：沪深300 同期 → 别拿"跑赢自己的对照组"当"跑赢市场"
3. **参数敏感性**：阈值换成 2%/5%/10% 结论是否翻转 → 3% 是不是调出来的
4. **收益归因**：钱是哪条腿赚的 → 动态持仓下"涨得最多的"常常不是"赚得最多的"

每一块报告怎么算/怎么打印在 report_portfolio_parts.py，本文件只管总装顺序。
"""

import pandas as pd

from quant.portfolio import align_prices, load_portfolio_navs, run_portfolio_backtest
from quant.rebalance import buy_and_hold, resolve_weights
from quant.report_attribution import print_contrib
from quant.report_portfolio_parts import (get_portfolio, load_bench, perf_row,
                                          print_trades, print_weights,
                                          threshold_sensitivity)


def run_portfolio_experiment(name, start=None, cost=0.001, initial_cash=10000.0,
                             decide_override=None, bench="沪深300", sensitivity=True,
                             plot=True):
    """run.py 组合模式总装：取数 → 回测 → 对照组 → 报告 → 图。"""
    p = get_portfolio(name)
    decide = decide_override if decide_override is not None else p.decide_fn
    navs = load_portfolio_navs(p.holdings, data_start=p.data_start, adjust=p.adjust)

    eq, weights, log = run_portfolio_backtest(navs, decide, start=start, cost=cost,
                                              initial_cash=initial_cash)
    # 对照组：权重照抄（工厂参数里有就取，取不到按等权），但建仓后不再动手
    w0 = (getattr(decide, "params", {}) or {}).get("weights")
    eq_hold, _w2, _l2 = run_portfolio_backtest(navs, buy_and_hold(weights=w0),
                                               start=start, cost=cost,
                                               initial_cash=initial_cash)
    bench_eq = load_bench(bench, eq)

    desc = getattr(decide, "desc", None) or p.decide_desc()
    if decide_override is not None:
        desc += "（PORTFOLIO_OVERRIDE 覆盖）"
    print(f"\n{'=' * 78}\n组合回测：{name}\n{'=' * 78}")
    print(f"成分：{' + '.join(f'{k}({v})' for k, v in p.holdings.items())}")
    print(f"决策：{desc}")
    print(f"区间：{eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}"
          f"（{(eq.index[-1] - eq.index[0]).days / 365.25:.1f} 年）   "
          f"初始 {initial_cash:.0f} 元   成本：双边各 {cost:.1%}   T 日决策 → T+1 净值成交")
    if p.note:
        print(f"档案备注：{p.note}")

    rows = [perf_row(eq, "本策略", initial_cash),
            perf_row(eq_hold, "对照·建仓后不再平衡", initial_cash)]
    if bench_eq is not None:
        rows.append(perf_row(bench_eq, f"基准·{bench}", initial_cash))
    tbl = pd.DataFrame(rows).set_index("口径")
    print(f"\n{tbl.to_string()}")
    print_trades(log, initial_cash, cost, eq)
    print_weights(weights)
    print_contrib(name, eq, weights, log, initial_cash)
    if len(log) - 1 < 10:
        print(f"⚠ 样本量警报：仅 {max(len(log) - 1, 0)} 次再平衡，"
              f"统计意义弱，结论按「方向性参考」理解")
    if sensitivity:
        threshold_sensitivity(navs, decide, start, cost, initial_cash)
    if plot:
        from quant.plot_portfolio import plot_portfolio_experiment
        plot_portfolio_experiment(name, eq, eq_hold, navs, weights, log, bench_eq,
                                  bench_name=bench, desc=desc,
                                  target_weights=resolve_weights(w0, list(p.holdings)))
    return tbl


def compare_portfolio_experiment(names, start=None, cost=0.001, initial_cash=10000.0,
                                 bench="沪深300"):
    """组合比选模式：几个配方同区间同起点对比（run.py 的名单写法）。

    注意起点：不同配方的成分成立时间不同，为了公平，统一从**最晚就绪**的那个
    配方的起点开始跑（否则"更早开始"本身就是优势，比的就不是策略了）。
    """
    ports = [get_portfolio(n) for n in names]
    navs = {n: load_portfolio_navs(p.holdings, data_start=p.data_start, adjust=p.adjust)
            for n, p in zip(names, ports)}
    starts = [align_prices(v)[1] for v in navs.values()]
    common = max(starts) if start is None else pd.Timestamp(start)
    how = "自动取最晚就绪日" if start is None else "你指定的 PF_START"
    print(f"\n统一起点 {common:%Y-%m-%d}（{how}；各配方成分就绪日 "
          f"{', '.join(f'{n}:{s:%Y-%m}' for n, s in zip(names, starts))}）")
    late = [n for n, s in zip(names, starts) if s > common]
    if late:                                # 指定起点早于某配方成分成立日 → 明确警告
        raise SystemExit(f"起点 {common:%Y-%m-%d} 早于 {late} 的成分成立日，"
                         f"这些配方跑不出来。把 PF_START 改晚一点或设 None（自动对齐）")

    results, rows = [], []
    for n, p in zip(names, ports):
        eq, w, log = run_portfolio_backtest(navs[n], p.decide_fn, start=common,
                                            cost=cost, initial_cash=initial_cash)
        results.append((n, eq, w, log))
        r = perf_row(eq, n, initial_cash)
        r["再平衡次数"] = max(len(log) - 1, 0)
        rows.append(r)
    bench_eq = load_bench(bench, results[0][1])
    if bench_eq is not None:
        rows.append({**perf_row(bench_eq, f"基准·{bench}", initial_cash), "再平衡次数": 0})
    print(f"\n{'=' * 78}\n组合比选：{' / '.join(names)}\n{'=' * 78}")
    print(pd.DataFrame(rows).set_index("口径").to_string())

    # 比选模式也报归因：同样的年化，可能一个是"全靠一条腿"、一个是"几条腿都出力"，
    # 前者对未来的依赖更集中（那条腿失灵策略就塌），只看年化看不出这个区别
    from quant.attribution import summary_table
    print("\n各配方的收益是谁贡献的（元，占总盈亏）：")
    for n, eq, w, log in results:
        try:
            tbl, _ = summary_table(eq, w, log, initial_cash)
        except (ValueError, AssertionError) as e:
            print(f"  {n}: 归因跳过（{type(e).__name__}）")
            continue
        parts = tbl.drop(index=["交易成本", "现金(不生息)"], errors="ignore")
        parts = parts.sort_values("贡献(元)", ascending=False)
        print(f"  {n}: " + "  ".join(f"{k}{v['贡献(元)']:+.0f}({v['占总盈亏']})"
                                     for k, v in parts.iterrows()))

    from quant.plot_portfolio import plot_portfolio_compare
    plot_portfolio_compare(results, bench_eq, bench_name=bench)
    return results
