# -*- coding: utf-8 -*-
"""
analysis/analyze_portfolio_attribution.py — 计划 23：组合收益归因**分段明细**

回答的问题："longterm_balance 这 12.9 年赚的钱，纳指/红利/黄金/中债各出了多少力？
每一年、每一次调仓之间，又分别是谁在出力？"

⚠ 全区间总账现在已经是**每次组合回测的默认输出**（run.py 跑组合就有，图上也有
"各成分累计贡献"那一联）。本脚本只在你想看**分段明细**时用：

    python analysis/analyze_portfolio_attribution.py                     # 默认 longterm_balance，按年
    python analysis/analyze_portfolio_attribution.py grid_3tier          # 换配方
    python analysis/analyze_portfolio_attribution.py longterm_balance rebalance   # 按每次再平衡分段

口径与守恒校验都在 quant/attribution.py 的文档串里（金额法 + 逐日断言）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from quant.portfolio import load_portfolio_navs, run_portfolio_backtest  # noqa: E402
from quant.report_attribution import print_attribution           # noqa: E402
from quant.report_portfolio_parts import get_portfolio     # noqa: E402

NAME = sys.argv[1] if len(sys.argv) > 1 else "longterm_balance"
BY = sys.argv[2] if len(sys.argv) > 2 else "Y"             # "Y" 按年 / "rebalance" 按调仓段
START = None            # None = 全部成分就绪日起（本脚本要看"全历史谁出力"，不截断）
COST = 0.001
INITIAL = 10000.0

p = get_portfolio(NAME)
navs = load_portfolio_navs(p.holdings, data_start=p.data_start, adjust=p.adjust)
eq, weights, log = run_portfolio_backtest(navs, p.decide_fn, start=START,
                                          cost=COST, initial_cash=INITIAL)
print_attribution(NAME, eq, weights, log, INITIAL, by=BY)

# —— 教学附注：把"贡献"和"自己涨了多少"分开看，是这张表的全部价值 ——
print("\n【怎么用这张表】")
print("1. 贡献高 ≠ 涨得多：仓位被再平衡压着，涨最猛的那条腿贡献会被削掉一截；")
print("   反过来，跌的时候被不断加仓的腿，反弹时贡献会超过它的仓位比例。")
print("2. 某条腿贡献长期为负、且与其他腿的相关性也不低 → 它在组合里没有位置"
      "（计划 21 判原油出局就是这个逻辑）。")
print("3. 但别只看贡献就删腿：低相关的腿的作用是压回撤（分母），"
      "光看分子（收益贡献）会把'保险'当成'累赘'。")
