# -*- coding: utf-8 -*-
"""
analyze_hongli_drop.py — 计划 26：中证红利该不该在 longterm_balance 里降权/剔除？

用户的问题（2026-08-14）：
  A. 中证红利指数还有没有长期投资价值？
  B. 四支柱策略里排除红利、或把 25% 降到更低，收益会不会更好？

回答方式（照计划 21 石油分析的四步法——那次是"加一条腿"，这次是"拆一条腿"）：
  ① 红利单资产长期表现：它自己赚钱吗（全区间 + 近 3 年）？
     净值（全收益）vs 价格指数的差 = 分红留存——这是"长期价值"的量化定义
  ② 相关性矩阵：红利和另外三腿还不同步吗？（低相关是它留在组合里的理由）
  ③ 分年拆解：基线 25% vs 剔除红利 两个配方的分年收益——红利哪年帮了组合、哪年拖累
  ④ 权重扫描：红利权重 0/10/15/20/25%（0=剔除，其余三腿等分剩下），主区间 + 近 3 年
     ⚠ 事后在同一段历史上试参数，天然有过拟合风险：只回答"历史上怎样"，不保证未来

估值口径：红利"贵不贵"的尺子是股息率（跑 analysis/analyze_hongli_valuation.py 取最新值）。
2026-08-13 实测：点位 5464（历史分位 92%）但股息率 4.60%（经验中枢 4%~5.5% 的正常偏高区）、
市盈率 8.18——估值不贵，点位由分红撑起来。

跑法：python analysis/analyze_hongli_drop.py
"""
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from fetch_data import fetch_index_daily_tx
from quant import metrics
from quant.data import load_data
from quant.portfolio import load_portfolio_navs, run_portfolio_backtest
from quant.rebalance import threshold_rebalance

COST, INITIAL = 0.001, 10000.0
# 纳指用广发 270042 做回测代理（建信跟踪差 + 额度问题见配方注释；计划 24 的既定口径）
ASSETS = {
    "纳指": "fund:270042",
    "中证红利": "fund:090010",
    "黄金": "fund:000216",
    "中债综合": "fund:161119",
}
FULL = "2013-08-22"   # 四腿齐的起点（黄金基金成立日）——所有配方统一从此起，保证公平
SUB = "2023-08-01"    # 近 3 年子区间：红利 2023 大牛之后，还值不值得拿
SUB_LABEL = "近3年(2023-08~今)"


def ann_ret(s):
    return metrics.annual_return(s)


def run_case(holdings, weights, start):
    """跑一个配方：等权重写 None（自动 1/n），降权写显式 weights。"""
    nv = load_portfolio_navs(holdings, data_start="20130101")
    eq, _w, _l = run_portfolio_backtest(
        nv, threshold_rebalance(weights=weights, threshold=0.03),
        start=start, cost=COST, initial_cash=INITIAL)
    return eq


def perf(eq):
    ret = eq.pct_change().dropna()
    return {"年化": f"{ann_ret(eq):+.2%}",
            "最大回撤": f"{metrics.max_drawdown(eq):.1%}",
            "年化波动": f"{ret.std() * np.sqrt(252):.1%}",
            "夏普": f"{metrics.sharpe_ratio(eq):.2f}",
            "卡玛": f"{metrics.calmar_ratio(eq):.2f}"}


def yearly_table(curves):
    """多配方分年收益表（读法：看每行哪列最大/最小 → 谁在帮、谁在拖）。"""
    rows = []
    for y in sorted({d.year for d in curves[list(curves)[0]].index}):
        row = {"年份": y}
        for k, s in curves.items():
            prev = s.loc[:f"{y - 1}-12-31"]
            win = s.loc[f"{y}-01-01":f"{y}-12-31"]
            if len(win) == 0:
                row[k] = None
            else:
                base = prev.iloc[-1] if len(prev) else win.iloc[0]
                row[k] = win.iloc[-1] / base - 1
        rows.append(row)
    return pd.DataFrame(rows).set_index("年份")


def scan(holdings_all, start):
    """权重扫描：红利权重 0（剔除）/10/15/20/25%，其余三腿等分剩下的。"""
    rows = []
    for w in [0.0, 0.10, 0.15, 0.20, 0.25]:
        holdings = dict(holdings_all)
        if w == 0:
            holdings.pop("中证红利")          # 剔除：三腿自动等权 1/3
            weights = None
        else:
            rest = (1 - w) / 3               # 降权：其余三腿等分剩余
            weights = {"纳指": rest, "黄金": rest,
                       "中债综合": rest, "中证红利": w}
        eq = run_case(holdings, weights, start)
        rows.append({"红利权重": f"{w:.0%}", **perf(eq)})
    return pd.DataFrame(rows)


def main():
    print(f"\n{'=' * 78}\n① 红利单资产长期表现（组合的收益来源，最终是各成分自己）"
          f"\n{'=' * 78}")
    nav = load_portfolio_navs(ASSETS, data_start="20130101")
    px = pd.DataFrame({k: v["close"] for k, v in nav.items()})
    ret = px.pct_change().dropna()
    for label, s in [(f"全区间({FULL}~今)", px.loc[FULL:]),
                     (SUB_LABEL, px.loc[SUB:])]:
        rows = []
        for k in px.columns:
            ss = s[k].dropna()          # 并集日期里某腿可能缺最后一天（QDII 滞后），先清空再算
            rows.append({"资产": k, "总收益": f"{ss.iloc[-1] / ss.iloc[0] - 1:+.1%}",
                         "年化": f"{ann_ret(ss):+.2%}",
                         "最大回撤": f"{metrics.max_drawdown(ss):.1%}",
                         "夏普": f"{metrics.sharpe_ratio(ss):.2f}"})
        print(f"\n—— {label} ——")
        print(pd.DataFrame(rows).set_index("资产").to_string())

    # 净值（全收益）vs 价格指数：差值 = 分红留存，"长期价值"的量化来源
    # 指数用腾讯源：东财/新浪对部分中证指数只回传旧数据（2019 年截止），腾讯源可取 2005~今
    df_fund, _i = load_data("fund:090010", start="20130101")
    idx = fetch_index_daily_tx("000922")
    idx_idx = pd.to_datetime(idx["date"])
    f_series = df_fund["close"].reindex(idx_idx).ffill()   # 基金净值对齐到指数日期
    both = pd.DataFrame({"基金净值(全收益)": f_series, "价格指数": idx["close"].values},
                        index=idx_idx).dropna().loc[FULL:]
    f, p = both["基金净值(全收益)"], both["价格指数"]
    print(f"\n分红留存（净值全收益 vs 价格指数，{FULL}~今）："
          f"基金累计 {f.iloc[-1]/f.iloc[0]-1:+.1%} vs 价格指数 {p.iloc[-1]/p.iloc[0]-1:+.1%}"
          f" → 分红贡献 {f.iloc[-1]/f.iloc[0] - p.iloc[-1]/p.iloc[0]:+.1%}")
    print("读法：红利基金的价格长期可能是横的，但分红被再投资进净值——"
          "股息率 4.6% 的年化分红就是这条腿长期收益的地板。")

    print(f"\n{'=' * 78}\n② 相关性：红利与另外三腿还不同步吗（低相关是它留在组合的理由）"
          f"\n{'=' * 78}")
    for label, rr in [(f"全区间({FULL}~今)", ret.loc[FULL:]),
                      (SUB_LABEL, ret.loc[SUB:])]:
        print(f"\n—— {label} 日收益率相关系数 ——")
        print(rr.corr().round(2).to_string())
        print("读法：红利的尺子不是点位而是股息率，它和纳指/黄金不同源；"
              "相关系数显著低于 1 就仍在对冲（计划 24 实测四腿 -0.05~0.12 属最优分散结构）。")

    print(f"\n{'=' * 78}\n③ 分年拆解：红利哪年帮了组合、哪年拖累"
          f"\n   （基线 25% vs 剔除红利 + 红利资产本身，对得上因果）\n{'=' * 78}")
    curves = {
        "基线(红利25%)": run_case(dict(ASSETS), None, FULL),
        "剔除红利(三腿)": run_case({k: v for k, v in ASSETS.items() if k != "中证红利"},
                                 None, FULL),
        "·红利资产本身": px["中证红利"].loc[FULL:],
    }
    df = yearly_table(curves)
    print(df.map(lambda x: "  —  " if x is None else f"{x:+.1%}").to_string())
    print("读法：哪年「剔除红利」明显好于基线，说明那年红利是包袱；"
          "哪年明显差，说明红利在顶住（如 A 股熊市的低相关缓冲）。")

    print(f"\n{'=' * 78}\n④ 权重扫描（事后探索，不是结论！）"
          f"\n   ⚠ 在同一段历史上试参数，天然有过拟合风险；"
          f"\n     它只能回答「历史上什么权重好」，不能保证未来。\n{'=' * 78}")
    for label, start in [(f"全区间({FULL}~今)", FULL), (SUB_LABEL, SUB)]:
        print(f"\n—— {label} ——")
        print(scan(ASSETS, start).set_index("红利权重").to_string())
    print("\n读法：看夏普/卡玛（每承担一份风险换来多少收益）。"
          "若红利降权后年化/夏普只升不降，说明这段历史里 25% 偏高了；"
          "若剔除后回撤明显变大，说明红利在管着波动。")


if __name__ == "__main__":
    main()
