# -*- coding: utf-8 -*-
"""
analyze_new_leg_candidates.py — 计划 27：给 longterm_balance 找新腿

用户的问题（2026-08-14）：除了现有四支柱（纳指/中证红利/黄金/中债），还有没有
相关性低、又有长期增长价值的基金？

判断框架（计划 21 沉淀，低相关是**必要**非充分条件）：
  ① 相关性低：和四条腿都不同步（进组合的入场券）
  ② 自身长期赚钱：年化/回撤/夏普（低相关但自己太差 → 白占仓位，石油就是反例）
  ③ 买得到：支付宝场外、不限购（QDII 大多限购，计划 23 实测纳指全行业买不进量）
     限购已用 fund_limit.py 逐个查过，结果标注在 CANDIDATES 注释里

候选（按"节奏"选，避免同一个东西换包装——红利低波 0.92、国开债 0.89 就是反例）：
  - 港股宽基：华夏恒生ETF联接A 000071（指数型，不限购 ✓）
  - 印度新兴：工银印度基金人民币 164824（**主动型** ⚠，50万/日 ≈ 不限 ✓，2018 成立数据短）
  - 德国发达：华安德国DAX联接A 000614（指数型，300 元/日，慢但可行）
  - A股大盘：易方达沪深300ETF联接A 110020（指数型，不限）
  - A股中盘：南方中证500ETF联接A 160119（指数型，不限）
  - 可转债：兴全可转债 340001（**主动型** ⚠，2004 成立历史最长）
  已出局（限购）：标普500（10 元/日）、日经225（10 元/日）、原油/石油股（计划 21：
  低相关但自身年化仅 +6.3%、回撤 -76.5%）

跑法：python analysis/analyze_new_leg_candidates.py
"""
import sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from quant import metrics
from quant.portfolio import load_portfolio_navs, run_portfolio_backtest
from quant.rebalance import threshold_rebalance

FULL = "2013-08-22"     # 四腿齐的起点
SUB = "2023-08-01"      # 近 3 年
LEGS = {"纳指": "fund:270042", "中证红利": "fund:090010",
        "黄金": "fund:000216", "中债综合": "fund:161119"}
# 候选顺序：节奏越"新"越靠前；note 里标注限购与基金性质
CANDIDATES = [
    ("恒生指数", "fund:000071",  "华夏恒生ETF联接A｜指数型｜不限购 ✓"),
    ("印度",     "fund:164824",  "工银印度人民币｜⚠主动型｜≈不限购(50万/日)｜2018成立"),
    ("德国DAX",  "fund:000614",  "华安德国DAX联接A｜指数型｜300元/日"),
    ("沪深300",  "fund:110020",  "易方达沪深300联接A｜指数型｜不限"),
    ("中证500",  "fund:160119",  "南方中证500联接A｜指数型｜不限"),
    ("可转债",   "fund:340001",  "兴全可转债｜⚠主动型｜不限｜2004成立"),
]


def main():
    print("\n=== 候选基金 vs 现有四腿：相关性 + 长期表现 ===")
    for label, _code, c in CANDIDATES:
        print(f"  {label}: {c}")

    # ---------- 取数（走轮子，自动缓存/体检/增量更新）----------
    hold = {**LEGS, **{name: code for name, code, _note in CANDIDATES}}
    navs = load_portfolio_navs(hold, data_start="20130101")
    px = pd.DataFrame({k: v["close"] for k, v in navs.items()})
    ret = px.pct_change().dropna()

    # ---------- ① 长期表现（成立以来全区间 + 近3年）----------
    print(f"\n{'=' * 78}\n① 单资产长期表现（低相关只是入场券，自己得先赚钱）"
          f"\n{'=' * 78}")
    for label, s_full in [("成立以来(各候选自己最长区间)",
                           px.loc[FULL:]), (SUB, px.loc[SUB:])]:
        print(f"\n—— {label} ——")
        rows = []
        for k in px.columns:
            ss = s_full[k].dropna()
            if len(ss) == 0:
                continue
            yrs = (ss.index[-1] - ss.index[0]).days / 365.25
            rows.append({"资产": k, "样本年数": f"{yrs:.1f}",
                         "总收益": f"{ss.iloc[-1]/ss.iloc[0]-1:+.1%}",
                         "年化": f"{metrics.annual_return(ss):+.2%}",
                         "最大回撤": f"{metrics.max_drawdown(ss):.1%}",
                         "夏普": f"{metrics.sharpe_ratio(ss):.2f}"})
        print(pd.DataFrame(rows).set_index("资产").to_string())
        print("读法：① 数据够长吗（<7 年样本量警报）？② 年化有没有 6%+？"
              "③ 回撤会不会比黄金还狠？三项都过才算有「长期增长价值」的候选。")

    # ---------- ② 相关性（重叠区间）----------
    print(f"\n{'=' * 78}\n② 相关性：候选和四条腿不同步吗（越低越能对冲）"
          f"\n{'=' * 78}")
    for label, s in [(f"全区间({FULL}~今)", ret.loc[FULL:]),
                     (SUB, ret.loc[SUB:])]:
        print(f"\n—— {label} 日收益率相关系数 ——")
        corr = s.corr().round(2)
        cols = list(LEGS) + [k for k, _v, _n in CANDIDATES]
        cols = [c for c in cols if c in corr.columns]
        print(corr.loc[cols, cols].to_string())
        print("读法：看候选那一列与前四条腿的相关系数——"
              "全部 <0.3 算「低相关」；>0.6 就是近亲（如红利低波 0.92），"
              "换进去不增加分散。")

    # ---------- ④ 组合级验证：加它 vs 不加它（同起点公平对比）----------
    print(f"\n{'=' * 78}\n③ 组合级验证：每个候选以 20% 加进组合，与不加它对比"
          f"\n   起点 = 加入后五腿对齐日（各自不同，所以基线也在同一日起重跑）"
          f"\n   ⚠ 事后探索，不是结论；但它能回答「加了到底涨不涨」"
          f"\n{'=' * 78}")
    COST, INITIAL = 0.001, 10000.0

    def run_one(holdings, start=None):
        nv = load_portfolio_navs(holdings, data_start="20130101")
        eq, _w, _l = run_portfolio_backtest(
            nv, threshold_rebalance(weights=None, threshold=0.03),
            start=start, cost=COST, initial_cash=INITIAL)
        return eq

    rows = []
    for name, code, note in CANDIDATES:
        try:
            eq_plus = run_one({**LEGS, name: code})           # 五腿等权 20%
        except ValueError:
            rows.append({"候选": name, "起点": "数据不足,跳过",
                         **{k: "—" for k in ["基线年化", "加后年化", "基线回撤",
                                             "加后回撤", "基线夏普", "加后夏普"]}})
            continue
        start = f"{eq_plus.index[0]:%Y-%m-%d}"                # 加后组合的实际起点
        eq_base = run_one(dict(LEGS), start=start)            # 基线四腿同起点重跑（对齐！）
        rows.append({"候选": name, "起点": start,
                     "基线年化": f"{metrics.annual_return(eq_base):+.2%}",
                     "加后年化": f"{metrics.annual_return(eq_plus):+.2%}",
                     "基线回撤": f"{metrics.max_drawdown(eq_base):.1%}",
                     "加后回撤": f"{metrics.max_drawdown(eq_plus):.1%}",
                     "基线夏普": f"{metrics.sharpe_ratio(eq_base):.2f}",
                     "加后夏普": f"{metrics.sharpe_ratio(eq_plus):.2f}"})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n读法：加后年化/夏普比基线高 → 这条腿在这段历史里在帮忙；"
          "加后年化降、回撤升 → 白占仓位甚至拖后腿（石油 5% 权重就把回撤拉到 -20.5%）。")

    # ---------- ⑤ 一句话结论模板 ----------
    print(f"\n{'=' * 78}\n④ 结论（框架）：\n"
          f"  进组合的标准 = 相关性低（<0.3）× 自己赚钱（年化6%+）× 买得到（不限购）\n"
          f"  三个条件缺一不可：低相关+自身差=石油（计划21：年化6.3%但回撤-76.5%）；\n"
          f"  自身好+高相关=红利低波/国开债（0.92/0.89，是近亲不是新腿）；\n"
          f"  全过但买不到=标普500/日经（10元/日，建仓2500元要1年）\n"
          f"  上面 ①② 的数据填进这个表，谁全过谁才是候选。"
          f"\n{'=' * 78}")


if __name__ == "__main__":
    main()
