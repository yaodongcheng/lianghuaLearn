# -*- coding: utf-8 -*-
"""
quant/rebalance.py — ③ 决策层：组合策略的"打法工厂"（与 signals.py / exits.py 平级）

组合策略的契约（与单标的策略对齐着看，就明白为什么这么设计）：

    单标的：entry_fn(df) -> 布尔 Series          "今天要不要买"
            exit_fn(pos, row, hist) -> str|None  "今天要不要卖"
    组合：  decide_fn(ctx) -> {标的: 带符号金额}  "今天每只买多少 / 卖多少钱"
                                                 正=买入金额，负=卖出金额，
                                                 返回 None 或 {} = 今天什么都不做

只有一个决策函数、而不是"买函数+卖函数"，是因为组合里**同一天必然同时有买有卖**
（卖超配的、买低配的），拆成两个函数反而要在外面同步它们。

引擎（portfolio.py）只负责纪律：T 日收盘决策 → T+1 收盘/净值成交、扣成本、记账；
决策函数拿到的 ctx 只包含**今天及以前**的数据，物理上偷不到未来 → 防未来函数。

本文件是决策函数的**工厂**（返回函数的函数），和 ExitSpec 一样：参数在外面填，
纪律封在里面，配方文件（quant/portfolios/*.py）只写"用哪种打法 + 什么参数"。
"""

def resolve_weights(weights, names):
    """weights=None → 等权展开；给了就校验合计=1 且标的对得上。"""
    if weights is None:
        return {n: 1 / len(names) for n in names}
    if set(weights) != set(names):
        raise ValueError(f"目标权重的标的 {sorted(weights)} 与组合成分 {sorted(names)} 不一致")
    total = sum(weights.values())
    if abs(total - 1) > 1e-9:
        raise ValueError(f"目标权重合计必须=1，实际 {total:.4f}")
    return dict(weights)


def _tag(fn, desc, factory, params):
    """给决策函数贴标签：报告回显用 desc，敏感性扫描用 factory+params 重建同款函数。"""
    fn.desc = desc
    fn.factory = factory
    fn.params = params
    return fn


# ============================ 打法 1：阈值再平衡 ============================

def threshold_rebalance(weights=None, threshold=0.03, min_trade_value=0.0):
    """阈值触发再平衡（知乎"长周期均衡/波动ETF"两文的原始规则）。

    规则：仓位占比最高的一只 − 最低的一只 ≥ threshold 时，全体拉回目标权重。
    为什么这样能赚钱：涨多的被动减仓、跌多的被动加仓 = 机械化的低买高卖，
    且不需要预测——这是它和择时策略的本质区别。

    参数：
        weights:         {标的: 目标权重}，None = 等权
        threshold:       触发线（0.03 = 相差 3 个百分点）
        min_trade_value: 单标的调仓金额下限（元），低于此额该只不动
                         （原文纪律："调整金额过小就忽略，否则光给券商交佣金"）
    """
    def decide(ctx):
        w = resolve_weights(weights, ctx.names)
        if not ctx.invested:                     # 还是一堆现金 → 先按目标权重建仓
            return ctx.orders_for_weights(w)
        spread = ctx.weights.max() - ctx.weights.min()
        if spread < threshold:                   # 没歪够，不动手（长持的"长"就体现在这）
            return None
        orders = ctx.orders_for_weights(w)
        return {k: v for k, v in orders.items() if abs(v) >= min_trade_value}

    desc = f"权重极差 ≥{threshold:.0%} → 全体拉回目标权重"
    if min_trade_value:
        desc += f"（单只差额 <{min_trade_value:.0f} 元不动）"
    return _tag(decide, desc, threshold_rebalance,
                {"weights": weights, "threshold": threshold,
                 "min_trade_value": min_trade_value})


# ============================ 打法 2：买入持有（对照组）============================

def buy_and_hold(weights=None):
    """建仓一次后永不调仓——**再平衡的对照组**。

    每个再平衡结论都必须和它比：不比，你就不知道收益是"再平衡带来的"
    还是"这几个资产本来就涨"。
    """
    def decide(ctx):
        w = resolve_weights(weights, ctx.names)
        return ctx.orders_for_weights(w) if not ctx.invested else None

    return _tag(decide, "建仓后永不调仓（对照组）", buy_and_hold, {"weights": weights})


# ============================ 打法 3：定期再平衡 ============================

def periodic_rebalance(weights=None, freq="Y", min_trade_value=0.0):
    """按日历定期再平衡：freq="Y" 每年 / "Q" 每季 / "M" 每月的第一个交易日。

    与阈值触发的区别（值得亲手比一次）：
    - 定期：什么时候动手是**确定的**，但可能在权重只歪了 0.5% 时白交手续费
    - 阈值：只在真歪了才动手，但什么时候动手事先不知道
    """
    period = {"Y": "year", "Q": "quarter", "M": "month"}
    if freq not in period:
        raise ValueError(f"freq 只支持 {sorted(period)}，收到 {freq!r}")

    def decide(ctx):
        w = resolve_weights(weights, ctx.names)
        if not ctx.invested:
            return ctx.orders_for_weights(w)
        if len(ctx.hist) < 2:
            return None
        today, prev = ctx.date, ctx.hist.index[-2]
        # 跨期的第一个交易日就动手（只看今天和昨天，不看未来日历）
        cur = (today.year, getattr(today, period[freq]) if freq != "Y" else 0)
        last = (prev.year, getattr(prev, period[freq]) if freq != "Y" else 0)
        if cur == last:
            return None
        orders = ctx.orders_for_weights(w)
        return {k: v for k, v in orders.items() if abs(v) >= min_trade_value}

    name = {"Y": "每年", "Q": "每季", "M": "每月"}[freq]
    return _tag(decide, f"{name}首个交易日拉回目标权重", periodic_rebalance,
                {"weights": weights, "freq": freq, "min_trade_value": min_trade_value})


__all__ = ["threshold_rebalance", "buy_and_hold", "periodic_rebalance", "resolve_weights"]
