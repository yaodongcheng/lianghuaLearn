# -*- coding: utf-8 -*-
"""
analyze_recent_drop.py — 诊断"最近这一波在亏钱"到底是谁的问题。

用户观察：2026-07 之后组合净值在跌。
但"策略亏钱"有两种完全不同的原因，动作也完全不同：
  A. 市场整体在跌（基准也跌、成分基金也跌）→ 策略没坏，这叫"回撤"，是持仓资产的
     系统性风险，改策略基本没用（除非加择时）
  B. 只有本策略在跌（基准在涨）→ 策略真的失效或规则有问题，值得改
所以本脚本把同一段时间的 组合净值 / 基准 / 每只成分 摊在一起看。

另外补一件事：把回测按"分年 + 近期滚动窗口"切片。全区间年化 +10% 是一个平均数，
它天然掩盖了"最近一年其实在亏"——这就是用户看图能看出来、看表格看不出来的原因。

跑法：python analysis/analyze_recent_drop.py
"""
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from quant.portfolio import load_portfolio_navs, run_portfolio_backtest, align_prices
from quant.report_portfolio_parts import get_portfolio, load_bench
from quant import metrics

NAMES = ["longterm_balance", "bottom_reversal_fund"]
PF_START = "2018-01-01"
COST, INITIAL = 0.001, 10000.0


def seg_return(s, start, end=None):
    """区间收益率：取 [start, end] 内的首末值算涨跌幅（不足两个点返回 None）。"""
    w = s.loc[start:end] if end else s.loc[start:]
    if len(w) < 2:
        return None
    return w.iloc[-1] / w.iloc[0] - 1


def fmt(x):
    return "  —  " if x is None else f"{x:+.2%}"


def main():
    # ---------- 1. 复现 run.py 的两条净值曲线 ----------
    curves, navs_all = {}, {}
    for name in NAMES:
        p = get_portfolio(name)
        navs = load_portfolio_navs(p.holdings, data_start=p.data_start, adjust=p.adjust)
        eq, _w, log = run_portfolio_backtest(navs, p.decide_fn, start=PF_START,
                                             cost=COST, initial_cash=INITIAL)
        curves[name] = eq
        navs_all[name] = (p, navs, log)

    bench = load_bench("沪深300", curves[NAMES[0]])
    curves["基准·沪深300"] = bench

    last = min(s.index[-1] for s in curves.values())
    print(f"\n数据末日：{last:%Y-%m-%d}（今天 2026-07-28，基金净值有 1-2 天延迟是正常的）")

    # ---------- 2. 分年收益：看"平均数"底下藏了什么 ----------
    print(f"\n{'=' * 78}\n① 分年收益（全区间年化是这些数的平均，别被平均数骗了）\n{'=' * 78}")
    years = sorted({d.year for d in curves[NAMES[0]].index})
    rows = []
    for y in years:
        row = {"年份": y}
        for k, s in curves.items():
            # 用「上年最后一天」做起点才是真正的年度收益；首年用当年首日
            prev = s.loc[:f"{y - 1}-12-31"]
            base = prev.iloc[-1] if len(prev) else None
            win = s.loc[f"{y}-01-01":f"{y}-12-31"]
            if len(win) == 0:
                row[k] = None
            elif base is None:
                row[k] = win.iloc[-1] / win.iloc[0] - 1
            else:
                row[k] = win.iloc[-1] / base - 1
        rows.append(row)
    df = pd.DataFrame(rows).set_index("年份")
    print(df.applymap(fmt).to_string())

    # ---------- 3. 近期滚动窗口：用户说的"这一波"到底多深 ----------
    print(f"\n{'=' * 78}\n② 近期各窗口收益（用户观察的「这一波」）\n{'=' * 78}")
    windows = {"最近 20 个交易日": 20, "最近 60 个交易日": 60,
               "最近 120 个交易日": 120, "最近 250 个交易日(≈1年)": 250}
    rows = []
    for label, n in windows.items():
        row = {"窗口": label}
        for k, s in curves.items():
            row[k] = s.iloc[-n:].iloc[-1] / s.iloc[-n:].iloc[0] - 1 if len(s) > n else None
        rows.append(row)
    for label, st in [("2026 年至今", "2026-01-01"), ("2026-07 至今", "2026-07-01")]:
        rows.append({"窗口": label, **{k: seg_return(s, st) for k, s in curves.items()}})
    print(pd.DataFrame(rows).set_index("窗口").applymap(fmt).to_string())

    # ---------- 4. 归因：跌的是策略还是成分资产本身 ----------
    print(f"\n{'=' * 78}\n③ 成分资产同期涨跌（判断 A/B：市场在跌 还是 策略在跌）\n{'=' * 78}")
    for name in NAMES:
        p, navs, log = navs_all[name]
        print(f"\n[{name}] 成分：")
        rows = []
        for code, nav in navs.items():
            s = nav["close"]
            label = f"{code}({p.holdings[code]})"
            rows.append({"成分": label,
                         "2026至今": seg_return(s, "2026-01-01"),
                         "2026-07至今": seg_return(s, "2026-07-01"),
                         "最近60日": (s.iloc[-60:].iloc[-1] / s.iloc[-60:].iloc[0] - 1
                                    if len(s) > 60 else None)})
        rows.append({"成分": ">>> 组合净值",
                     "2026至今": seg_return(curves[name], "2026-01-01"),
                     "2026-07至今": seg_return(curves[name], "2026-07-01"),
                     "最近60日": (curves[name].iloc[-60:].iloc[-1]
                                / curves[name].iloc[-60:].iloc[0] - 1)})
        print(pd.DataFrame(rows).set_index("成分").applymap(fmt).to_string())

    # ---------- 5. 当前回撤位置：现在离历史最高点多远 ----------
    print(f"\n{'=' * 78}\n④ 当前回撤位置（对照历史最大回撤，判断这波是否「超纲」）\n{'=' * 78}")
    rows = []
    for k, s in curves.items():
        peak = s.cummax()
        cur_dd = s.iloc[-1] / peak.iloc[-1] - 1
        peak_date = s.loc[:s.index[-1]].idxmax()
        rows.append({"口径": k,
                     "当前回撤": f"{cur_dd:.2%}",
                     "历史最大回撤": f"{metrics.max_drawdown(s):.2%}",
                     "最高点日期": f"{peak_date:%Y-%m-%d}",
                     "距最高点": f"{(s.index[-1] - peak_date).days} 天"})
    print(pd.DataFrame(rows).set_index("口径").to_string())

    # ---------- 6. 最近的调仓动作：是不是在下跌里频繁买入 ----------
    print(f"\n{'=' * 78}\n⑤ 最近 5 次调仓（看策略在这波里做了什么）\n{'=' * 78}")
    for name in NAMES:
        _p, _navs, log = navs_all[name]
        print(f"\n[{name}] 共 {len(log) - 1} 次再平衡，最后 5 条：")
        print(log.tail(5).to_string())


if __name__ == "__main__":
    main()
