# -*- coding: utf-8 -*-
"""
analyze_hongli_vs_hs300.py — 计划 28：把红利的 25% 直接换成沪深300，会怎样？

问题（2026-08-14）：四腿结构不变，但 A 股腿从「中证红利」换成「沪深300」。
（动机推测：红利近 3 年平淡（年化 4.2%），沪深300 近 3 年反弹（年化 7.4%））

要回答三件事：
  ① 两条腿自己差多少（单资产：年化/回撤/夏普，全区间 + 近3年）
  ② 换完组合的分散结构变了吗（相关性矩阵：沪深300 与另外三腿的相关）
  ③ 换与不换，组合整体差多少（回测：全区间 + 近3年 + 分年拆解）
     ⚠ 近 3 年表现是"最近"的表现，拿它决定换腿 = 追涨（计划 26 已演示区间过拟合）

口径与配方一致：纳指用广发 270042 回测代理；等权 25%；阈值 3% 再平衡；
双边成本 0.1%；沪深300 = 易方达沪深300ETF联接A（110020）。

跑法：python analysis/analyze_hongli_vs_hs300.py
"""
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from quant import metrics
from quant.portfolio import load_portfolio_navs, run_portfolio_backtest
from quant.rebalance import threshold_rebalance

FULL = "2013-08-22"          # 四腿齐的起点
SUB = "2023-08-01"           # 近 3 年
COST, INITIAL = 0.001, 10000.0

ASSETS = {"纳指": "fund:270042", "黄金": "fund:000216", "中债综合": "fund:161119"}
HONGLI = {"中证红利": "fund:090010"}
HS300 = {"沪深300": "fund:110020"}


def run_one(holdings, start):
    nv = load_portfolio_navs(holdings, data_start="20130101")
    eq, _w, _l = run_portfolio_backtest(
        nv, threshold_rebalance(weights=None, threshold=0.03),
        start=start, cost=COST, initial_cash=INITIAL)
    return eq


def perf(eq):
    ret = eq.pct_change().dropna()
    return {"年化": f"{metrics.annual_return(eq):+.2%}",
            "最大回撤": f"{metrics.max_drawdown(eq):.1%}",
            "年化波动": f"{ret.std() * np.sqrt(252):.1%}",
            "夏普": f"{metrics.sharpe_ratio(eq):.2f}",
            "卡玛": f"{metrics.calmar_ratio(eq):.2f}"}


def main():
    # 取数一次，三处共用
    all_holdings = {**ASSETS, **HONGLI, **HS300}
    navs = load_portfolio_navs(all_holdings, data_start="20130101")
    px = pd.DataFrame({k: v["close"] for k, v in navs.items()})
    ret = px.pct_change().dropna()

    # ---------- ① 单资产：红利 vs 沪深300 ----------
    print(f"\n{'=' * 78}\n① 两条 A 股腿单挑（替换后，组合里 A 股就靠这一条）"
          f"\n{'=' * 78}")
    for label, s in [(f"全区间({FULL}~今)", px.loc[FULL:]),
                     (SUB, px.loc[SUB:])]:
        rows = []
        for k in ["中证红利", "沪深300", "纳指", "黄金", "中债综合"]:
            ss = s[k].dropna()
            rows.append({"资产": k, "总收益": f"{ss.iloc[-1]/ss.iloc[0]-1:+.1%}",
                         "年化": f"{metrics.annual_return(ss):+.2%}",
                         "最大回撤": f"{metrics.max_drawdown(ss):.1%}",
                         "夏普": f"{metrics.sharpe_ratio(ss):.2f}"})
        print(f"\n—— {label} ——")
        print(pd.DataFrame(rows).set_index("资产").to_string())

    # ---------- ② 相关性：沪深300 与另外三腿 ----------
    print(f"\n{'=' * 78}\n② 相关性（换完后组合里的分散结构）\n{'=' * 78}")
    for label, s in [(f"全区间({FULL}~今)", ret.loc[FULL:]),
                     (SUB, ret.loc[SUB:])]:
        print(f"\n—— {label} ——")
        print(s.corr().round(2).to_string())
        print("读法：红利 vs 沪深300 的相关系数 ≈ 0.7~0.75 → 它俩高度同源"
              "（都是 A 股）；但沪深300 与纳指/黄金/中债的相关性≈红利水平"
              "（都 <0.25）→ 换腿不破坏分散结构，只改变 A 股腿的风格。")

    # ---------- ③ 组合回测对比 ----------
    print(f"\n{'=' * 78}\n③ 组合整体：换 vs 不换（同起点、同参数，只换 A 股腿）"
          f"\n{'=' * 78}")
    curves = {
        "基线(红利25%)": run_one({**ASSETS, **HONGLI}, FULL),
        "换沪深300(25%)": run_one({**ASSETS, **HS300}, FULL),
    }
    rows = []
    for name, eq in curves.items():
        rows.append({"配方": name, **perf(eq)})
    # 近 3 年
    rows2 = []
    for name, eq in curves.items():
        eq3 = eq.loc[SUB:]
        rows2.append({"配方": name, **perf(eq3)})
    print("\n—— 全区间 ——")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n—— 近3年（⚠ 事后视角，不能当换腿依据）——")
    print(pd.DataFrame(rows2).to_string(index=False))

    # ---------- ④ 分年拆解 ----------
    print(f"\n{'=' * 78}\n④ 分年拆解：哪年换腿更好、哪年更差\n{'=' * 78}")
    curves2 = dict(curves)
    curves2["·红利资产本身"] = px["中证红利"].loc[FULL:]
    curves2["·沪深300本身"] = px["沪深300"].loc[FULL:]
    rows = []
    for y in sorted({d.year for d in curves["基线(红利25%)"].index}):
        row = {"年份": y}
        for k, s in curves2.items():
            prev = s.loc[:f"{y - 1}-12-31"]
            win = s.loc[f"{y}-01-01":f"{y}-12-31"]
            if len(win) == 0:
                row[k] = None
            else:
                base = prev.iloc[-1] if len(prev) else win.iloc[0]
                row[k] = win.iloc[-1] / base - 1
        rows.append(row)
    df = pd.DataFrame(rows).set_index("年份")
    print(df.map(lambda x: "  —  " if x is None else f"{x:+.1%}").to_string())
    print("读法：哪年「换沪深300」明显好于基线 → 那年 A 股风格在大盘成长；"
          "哪年明显差 → 那年高股息/防御在赢。看完整轮牛熊，别只看最近两年。")


if __name__ == "__main__":
    main()
