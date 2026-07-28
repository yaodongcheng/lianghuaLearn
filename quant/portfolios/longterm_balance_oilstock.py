# -*- coding: utf-8 -*-
"""组合：长周期均衡 + 一档**石油公司股票** —— 计划 21 的对照配方

与 longterm_balance_oil 只差一个成分，但换的是**资产的本质**：
    longterm_balance_oil       161129 原油 QDII-FOF   → 跟油价走（买期货 ETF）
    本配方（oilstock）         162411 华宝标普油气A   → 跟**美股油气公司股票**走

为什么要做这个对照（这是本计划最重要的教学点）：
很多人说"我看好油价，买个石油基金"，买到的其实是石油公司股票基金。两者区别：
- **油价涨，石油公司股票不一定同步涨**（公司还有成本、税、汇率、自身经营、美股大盘情绪）
- 石油公司股票**本质是股票**，与纳指、A股同涨同跌的成分高得多
  → 加进组合的"分散化收益"会明显小于原油
- 但反过来它**没有期货展期损耗**，长期持有不会被换月成本慢慢磨掉
所以哪个更适合进组合，不能拍脑袋，要看**相关性 + 实测**（见 analysis/analyze_oil_in_balance.py）。

162411 是 LOF（既能场内买也能场外申购），支付宝可申购，数据从 2011-09 起 ——
比原油基金早 5 年，所以它还能顺便回答"更长区间下结论是否一样"。

其余口径（阈值 3%、五等权 20%、成本双边 0.1%）与 longterm_balance_oil 完全一致，
只换成分 —— 这样两条曲线的差异只能来自资产本身，不来自参数。
"""
from quant import Portfolio
from quant.rebalance import threshold_rebalance

PORTFOLIO = Portfolio(
    name="longterm_balance_oilstock",
    holdings={
        "纳指": "fund:270042",
        "中证红利": "fund:090010",
        "黄金": "fund:000216",
        "中债综合": "fund:161119",
        "石油股": "fund:162411",     # 华宝标普油气A（QDII，美股油气上游公司股票）
    },
    decide_fn=threshold_rebalance(weights=None, threshold=0.03),
    data_start="20130101",
    note="计划 21 对照组：把 20% 给石油**公司股票**而非油价。无期货展期损耗，"
         "但与股市相关性高 → 分散效果待实测",
)
