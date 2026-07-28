# -*- coding: utf-8 -*-
"""
quant/grid.py — ③ 决策层：网格类决策函数工厂（与 rebalance.py 平级的另一个家族）

为什么网格能进组合契约（原先被判定"落不进框架"，这里给出日频版）：
网格的输出天然就是"这只标的今天买/卖多少钱"——正是 decide_fn(ctx) 的形状。
挡住它的只有**成交时点**：原版网格靠盘中条件单在【档位价】成交，而组合引擎
只有"T 日收盘决策 → T+1 收盘/净值成交"一种成交方式。

所以这里做的是**日频近似版**，三处差异必须知道（是差异不是 bug）：
1. 成交价：用次日收盘价，不是档位价 → 跳空大的日子会比原版吃亏或占便宜
2. 同日穿越多档：按当日收盘所处的档位一次性补齐，不模拟盘中来回
3. 破前高清仓：按【收盘】站上前高判定、次日收盘卖出，不是盘中触价卖

想要盘中触价的口径，看 analysis/analyze_grid_etf.py（自写事件循环那版）。
两版一起跑，差额就是"盘中限价单值多少钱"——这是这套东西真正的教学价值。

档位语义（与那个脚本一致）：以启动日收盘为锚点，第 k 档价 = 锚点 × (1−间距)^k，
下跌 k 增大 → 买，回升 k 减小 → 卖。买的份数 > 卖的份数 = 震荡中净吸筹
（作者的"持仓不死"）。买用 floor 定档、卖用 ceil 定档，所以价格在两档之间时
两边都不动手——否则会在同一档反复买卖。
"""

import numpy as np

# 原文三档：(间距, 下跌买入份数, 上涨卖出份数)
TIERS_ARTICLE = ((0.08, 8, 6), (0.15, 15, 12), (0.30, 30, 20))


def grid_ladder(ceiling=0.70, tiers=TIERS_ARTICLE, high_window=756,
                high_min_periods=250, portions=200):
    """三档网格决策函数（知乎"波动ETF策略"原文规则，单标的 + 现金）。

    参数（默认值全部照抄原文，不许"顺手调好一点"）：
        ceiling:          开仓闸门——收盘 ≤ ceiling × 滚动最高收盘才启动网格
        tiers:            三档 (间距, 买份数, 卖份数)
        high_window:      "前高"的回看窗口（756 个交易日 ≈ 3 年）
        high_min_periods: 窗口内至少这么多根 K 线才认前高（防新标的假高点）
        portions:         本金拆成多少份（原文 200 份 → 1 份 = 本金/200）

    只用一只标的：holdings 写一个成分即可（组合引擎允许留现金、允许分批，
    单标的引擎只有满仓/空仓两态，所以分批建仓类策略一律走这边）。
    """
    st = {}                                   # 网格状态（锚点/前高/各档档位）

    def decide(ctx):
        asset = ctx.names[0]
        if ctx.i == 0:                        # 每次回测第一天重置，重跑结果可复现
            st.clear()
            st.update(active=False, anchor=None, high=None, portion=ctx.total / portions,
                      k={t[0]: 0 for t in tiers})
            return None
        close = float(ctx.prices[asset])
        px = ctx.hist[asset]                  # 只到今天，看不到未来

        if not st["active"]:
            # —— 待命：今天收盘判定闸门，明天收盘才可能有第一笔成交 ——
            if len(px) < high_min_periods:
                return None
            roll_high = float(px.iloc[-high_window:].max())
            if close <= ceiling * roll_high:
                st.update(active=True, anchor=close, high=roll_high,
                          k={t[0]: 0 for t in tiers})
            return None

        # —— 破前高 → 全清，回到待命等下一次闸门 ——
        if close >= st["high"]:
            st.update(active=False, anchor=None, high=None)
            held = float(ctx.values[asset])
            return {asset: -held} if held > 1 else None

        # —— 网格运行中：按今日收盘所处档位补齐买卖 ——
        budget, order = ctx.cash, 0.0
        for step, buy_p, sell_p in tiers:
            r = 1 - step
            depth = np.log(close / st["anchor"]) / np.log(r)
            k_buy, k_sell = int(np.floor(depth)), int(np.ceil(depth))
            while st["k"][step] < k_buy:      # 又跌深了一档 → 买
                amt = buy_p * st["portion"]
                if amt > budget:              # 现金耗尽 = 原文"200 份用完"，自然封顶
                    break
                budget -= amt
                order += amt
                st["k"][step] += 1
            while st["k"][step] > k_sell:     # 涨回一档 → 卖
                order -= sell_p * st["portion"]
                st["k"][step] -= 1
        if order < 0:                         # 卖不超过持仓（引擎也会截断，这里先算准）
            order = -min(-order, float(ctx.values[asset]))
        return {asset: order} if abs(order) > 1 else None

    decide.desc = (f"三档网格（日频版）：收盘 ≤{ceiling:.0%}×{high_window // 252}年最高 → 启动，"
                   f"{'/'.join(f'{s:.0%}买{b}卖{sl}份' for s, b, sl in tiers)}，"
                   f"本金拆 {portions} 份，破前高全清")
    decide.factory = grid_ladder
    decide.params = {"ceiling": ceiling, "tiers": tiers, "high_window": high_window,
                     "high_min_periods": high_min_periods, "portions": portions}
    return decide


__all__ = ["grid_ladder", "TIERS_ARTICLE"]
