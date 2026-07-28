# -*- coding: utf-8 -*-
"""
quant/portfolio_fill.py — ④ 组合引擎的撮合零件：把订单变成真实的份数与现金

单独一个文件，是因为它是引擎里**唯一会"打折执行"策略意图**的地方，纪律都写在这：
- 先卖后买：卖单回笼的现金当天就能用于买入（实盘场外基金做不到这么顺，
  所以这里只在"同一天的调仓"内部这样处理，跨日仍然守 T+1）
- 卖不超过持仓（不许裸卖空）、买不超过现金（不许透支）→ 超了就自动截断，
  而不是报错。回测里能做到的事，实盘也得能做到，否则回测收益是假的
- 买卖都按成交额扣单边成本（与 engine.py 同口径）

买入口径注意：spend 是"花掉的钱"，扣完费才换成份数（份数 = spend×(1−cost)/净值），
卖出是"卖掉的市值"，回笼现金再扣费。两边都让成本落在投资者身上，不会白赚手续费。
"""

__all__ = ["fill_orders"]


def fill_orders(pending, names, price, shares, cash, cost):
    """执行一批订单（金额制）。**原地修改 shares**，返回 (traded, fee, cash)。

    参数：
        pending: {名称: 带符号金额}，正=买入金额、负=卖出金额（决策函数的输出）
        price:   今日各标的净值/价格（Series）
        shares:  当前持仓份数 dict（会被原地更新）
        cash:    当前现金
        cost:    单边成本率
    返回：
        traded: {名称: 实际成交的带符号金额}（被截断后的真实成交，不是意图）
        fee:    本次总手续费
        cash:   成交后的现金
    """
    traded, fee = {}, 0.0
    for n in names:                          # 先卖：回笼现金，且卖不超过持仓
        amt = pending.get(n, 0.0)
        if amt < 0:
            sell = min(-amt, shares[n] * price[n])
            if sell <= 0:
                continue
            shares[n] -= sell / price[n]
            cash += sell * (1 - cost)
            traded[n] = traded.get(n, 0.0) - sell
            fee += sell * cost
    for n in names:                          # 再买：买不超过现金（不许透支）
        amt = pending.get(n, 0.0)
        if amt > 0:
            spend = min(amt, cash)
            if spend <= 0:
                continue
            shares[n] += spend * (1 - cost) / price[n]
            cash -= spend
            traded[n] = traded.get(n, 0.0) + spend
            fee += spend * cost
    return traded, fee, cash
