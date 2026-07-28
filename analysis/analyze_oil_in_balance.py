# -*- coding: utf-8 -*-
"""
analyze_oil_in_balance.py — 计划 21：石油该不该进 longterm_balance

比选表已给出结论（年化不变、回撤翻倍），本脚本回答**为什么**，四件事：
  ① 相关性矩阵：加一个资产进组合，唯一的正当理由是"和现有资产不同步"。
     但相关性低只是必要条件，不是充分条件 —— 还得看这个资产自己长期是不是赚钱的。
  ② 单资产长期表现：原油基金自己的年化和回撤（暴露期货展期损耗的代价）
  ③ 分年拆解：石油在哪些年份帮了组合、哪些年份拖累（2020 负油价 / 2022 俄乌）
  ④ 权重扫描：如果非要加，加多少才不伤组合（明确标注这是**事后探索**，不是结论）

跑法：python analysis/analyze_oil_in_balance.py
"""
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from quant import metrics
from quant.portfolio import load_portfolio_navs, run_portfolio_backtest
from quant.rebalance import threshold_rebalance
from quant.report_portfolio_parts import get_portfolio

START, COST, INITIAL = "2018-01-01", 0.001, 10000.0

# 五类资产（含两种石油口径），统一在这里取数一次
ASSETS = {
    "纳指": "fund:270042",
    "中证红利": "fund:090010",
    "黄金": "fund:000216",
    "中债综合": "fund:161119",
    "原油(跟油价)": "fund:161129",
    "石油股(162411)": "fund:162411",
}


def ann_ret(s):
    return metrics.annual_return(s)


def main():
    navs = load_portfolio_navs(ASSETS, data_start="20160101")
    px = pd.DataFrame({k: v["close"] for k, v in navs.items()}).loc[START:].dropna()
    print(f"\n统一区间：{px.index[0]:%Y-%m-%d} ~ {px.index[-1]:%Y-%m-%d}"
          f"（{(px.index[-1] - px.index[0]).days / 365.25:.1f} 年，共 {len(px)} 个交易日）")

    # ---------- ① 相关性 ----------
    print(f"\n{'=' * 78}\n① 日收益率相关系数（越接近 0 越能互相对冲；越接近 1 越是同一个东西）"
          f"\n{'=' * 78}")
    ret = px.pct_change().dropna()
    print(ret.corr().round(2).to_string())
    print("\n读法：加资产进组合的正当理由是"
          "「和现有资产不同步」→ 看新资产那一列与前四类的相关系数。")

    # ---------- ② 单资产长期表现 ----------
    print(f"\n{'=' * 78}\n② 各资产单独持有的表现（组合的收益来源，最终还是各成分自己）"
          f"\n{'=' * 78}")
    rows = []
    for k in px.columns:
        s = px[k]
        rows.append({"资产": k,
                     "总收益": f"{s.iloc[-1] / s.iloc[0] - 1:+.1%}",
                     "年化": f"{ann_ret(s):+.2%}",
                     "最大回撤": f"{metrics.max_drawdown(s):.1%}",
                     "年化波动": f"{ret[k].std() * np.sqrt(252):.1%}",
                     "夏普": f"{metrics.sharpe_ratio(s):.2f}"})
    print(pd.DataFrame(rows).set_index("资产").to_string())

    # ---------- ③ 三个组合的分年收益 ----------
    print(f"\n{'=' * 78}\n③ 三配方分年收益（看石油在哪年帮忙、哪年拖累）\n{'=' * 78}")
    names = ["longterm_balance", "longterm_balance_oil", "longterm_balance_oilstock"]
    curves = {}
    for n in names:
        p = get_portfolio(n)
        nv = load_portfolio_navs(p.holdings, data_start=p.data_start, adjust=p.adjust)
        eq, _w, log = run_portfolio_backtest(nv, p.decide_fn, start=START,
                                            cost=COST, initial_cash=INITIAL)
        curves[n] = eq
    # 顺便把两种石油资产自己的分年也放进来，方便对上因果
    curves["·原油资产本身"] = px["原油(跟油价)"]
    curves["·石油股本身"] = px["石油股(162411)"]

    rows = []
    for y in sorted({d.year for d in curves[names[0]].index}):
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
    df = pd.DataFrame(rows).set_index("年份")
    print(df.map(lambda x: "  —  " if x is None else f"{x:+.1%}").to_string())

    # ---------- ④ 权重扫描（事后探索，非结论） ----------
    print(f"\n{'=' * 78}\n④ 石油权重扫描：加多少才不伤组合"
          f"\n   ⚠ 这是**事后在同一段历史上试参数**，天然有过拟合风险。"
          f"\n     它只能回答「历史上多少合适」，不能保证未来。\n{'=' * 78}")
    base4 = {"纳指": "fund:270042", "中证红利": "fund:090010",
             "黄金": "fund:000216", "中债综合": "fund:161119"}

    def run_case(holdings, weights):
        nv = load_portfolio_navs(holdings, data_start="20160101")
        eq, _w, _l = run_portfolio_backtest(
            nv, threshold_rebalance(weights=weights, threshold=0.03),
            start=START, cost=COST, initial_cash=INITIAL)
        return {"年化": f"{ann_ret(eq):+.2%}",
                "最大回撤": f"{metrics.max_drawdown(eq):.1%}",
                "夏普": f"{metrics.sharpe_ratio(eq):.2f}",
                "卡玛": f"{metrics.calmar_ratio(eq):.2f}"}

    # 基线（无石油）只跑一次
    rows = [{"石油口径": "（无石油·基线）", "石油权重": "0%", **run_case(dict(base4), None)}]
    for oil_key, oil_code in [("原油(跟油价)", "fund:161129"),
                              ("石油股(162411)", "fund:162411")]:
        for w_oil in [0.05, 0.10, 0.15, 0.20]:
            holdings = {**base4, "石油": oil_code}
            rest = (1 - w_oil) / 4                    # 其余四类等分剩下的
            weights = {"纳指": rest, "中证红利": rest, "黄金": rest,
                       "中债综合": rest, "石油": w_oil}
            rows.append({"石油口径": oil_key, "石油权重": f"{w_oil:.0%}",
                         **run_case(holdings, weights)})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n读法：看夏普/卡玛（每承担一份风险换来多少收益）。"
          "如果加石油后夏普只降不升，说明这个资产在这段历史里对组合没有贡献。")


if __name__ == "__main__":
    main()
