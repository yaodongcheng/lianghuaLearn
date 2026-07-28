# -*- coding: utf-8 -*-
"""
analysis/analyze_zhihu_portfolios.py — 计划 16：知乎两个组合配方的复现实验

⚠ 2026-07-28（计划 17）重构：组合回测的报告/图/敏感性已全部搬进框架
   （quant/report_portfolio.py + quant/plot_portfolio.py），配方搬进
   quant/portfolios/。本脚本现在只是**一键复现这两个配方**的薄壳，
   逻辑一行都不在这里——想改参数请用 run.py 的 PORTFOLIO_OVERRIDE。

两个配方同为"4 资产等权 + 权重极差 ≥3% 触发再平衡"，只是成分不同：
- longterm_balance_v1 原版：纳指 + 红利低波 + 黄金 + 豆粕（2020-01 起，豆粕最晚成立）
  ⚠ 该配方原名 volatile_etf，2026-07-28 更名（原名是笔误，真正的"波动ETF策略"
    是三档网格 → quant/portfolios/grid_3tier.py）
- longterm_balance 调整版：纳指 + 中证红利 + 黄金 + 中债综合（2013-08 起，黄金最晚）

口径（与原作者的差异，重要）：
- 场内 ETF 前复权数据被企业防火墙断连 → 改用**场外联接基金累计净值**（含分红，
  等价全收益口径）。这正是支付宝实操渠道，但收益略低于场内 ETF（联接基金持
  5~10% 现金 + 申赎费影响），回测结果是"保守版"。
- 成本双边各 0.1%；初始资金 10000 元；每个配方自带"不再平衡"对照组。

运行：python analysis/analyze_zhihu_portfolios.py
产出：终端报告 + data/portfolio_longterm_balance_v1.png / portfolio_longterm_balance.png
      + 两配方比选图（统一起点，公平起跑）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from quant.report_portfolio import (compare_portfolio_experiment,
                                    run_portfolio_experiment)

NAMES = ["longterm_balance", "longterm_balance_v1"]
COST = 0.001
INITIAL = 10000.0

if __name__ == "__main__":
    for name in NAMES:
        run_portfolio_experiment(name, cost=COST, initial_cash=INITIAL)
    # 两配方对比：起点自动取最晚就绪日（豆粕 2020-01），否则"开始得早"本身就是优势
    compare_portfolio_experiment(NAMES, cost=COST, initial_cash=INITIAL)
