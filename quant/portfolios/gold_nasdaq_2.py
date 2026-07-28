# -*- coding: utf-8 -*-
"""组合：纳指 + 黄金 五五开（**新建组合的最小模板**，同时是消融实验）

这个文件的两个用途：
1. **模板**：想试自己的配方 → 复制本文件、改 holdings 和 decide_fn 两处，
   再去 quant/portfolios/__init__.py 加两行登记，run.py 填名字就能跑。
2. **消融实验（ablation）**：把 longterm_balance 的四资产砍到两个——只留
   "美股成长 + 避险黄金"这对最经典的低相关组合，看红利和债券那两条腿
   到底贡献了什么。做法是每次只改一个变量，这样结论才归因得清楚。

⚠ 本配方尚未实测，note 里没有绩效数字就是"还没验过"，别当结论用。
"""
from quant import Portfolio
from quant.rebalance import threshold_rebalance

PORTFOLIO = Portfolio(
    name="gold_nasdaq_2",
    holdings={
        "纳指": "fund:270042",
        "黄金": "fund:000216",
    },
    # 等权 50/50；想试 60/40 就写 weights={"纳指": 0.6, "黄金": 0.4}
    # 想换打法就换工厂：buy_and_hold() / periodic_rebalance(freq="Y")
    decide_fn=threshold_rebalance(weights=None, threshold=0.03),
    data_start="20130101",
    note="消融实验用：四资产砍到两资产，看红利+债券两条腿的贡献（未实测）",
)
