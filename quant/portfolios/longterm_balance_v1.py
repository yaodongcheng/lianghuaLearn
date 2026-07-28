# -*- coding: utf-8 -*-
"""组合：长周期均衡持有【原版·豆粕】（知乎「首席评论员」最初版本，计划 16 验证 ✓）

⚠ 命名历史（2026-07-28 更正）：本文件原名 volatile_etf.py，是当初把
「波动ETF策略.md」误复制成「长周期均衡持有策略.md」内容时起的名字。
文件内容一直是对的（长周期均衡的第一版配方），只有名字骗人，故改名。
真正的"波动ETF策略"（三档条件单网格）在 quant/portfolios/grid_3tier.py。

同一作者的第一版配方：纳指 + 红利低波 + 黄金 + **豆粕** 各 25%，3% 阈值再平衡。
后来他自己把豆粕换成国债（→ longterm_balance），理由是：豆粕近年只震荡不涨，
只贡献对冲不贡献收益，且成立晚导致回测期太短，有"踩中行情"的过拟合嫌疑。

留着这个文件的意义是**对照实验**：同一套纪律，只换一个成分，结果差多少。
"""
from quant import Portfolio
from quant.rebalance import threshold_rebalance

PORTFOLIO = Portfolio(
    name="longterm_balance_v1",
    holdings={
        "纳指": "fund:270042",
        "红利低波": "fund:007466",   # 华泰柏瑞红利低波ETF联接（比中证红利多了低波因子）
        "黄金": "fund:000216",
        "豆粕": "fund:007937",       # 华夏饲料豆粕ETF联接（唯一的农产品期货 ETF）
    },
    decide_fn=threshold_rebalance(weights=None, threshold=0.03),
    data_start="20190101",  # 豆粕基金 2020-01 成立 → 组合实际从 2020-01-13 起
    note="实测 2020-01~2026-07（6.5年）：年化 +13.87%、回撤 -10.2%、夏普 1.16；"
         "但窗口短且踩中黄金牛市，作者本人认有过拟合嫌疑 → 别只看年化比国债版高",
)
