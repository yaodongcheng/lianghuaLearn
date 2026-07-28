# -*- coding: utf-8 -*-
"""
quant/adapter.py — ③ 决策层：把【单标的择时策略】翻译成【组合决策函数】

为什么需要它：
run.py 两种模式不能混搭（单标的图画"价格+买卖点"，组合图画"净值+权重漂移"，
硬拼一张图会误读）。想把择时策略和资产配置组合放同一张净值图上比，
就得让择时策略说组合契约的话——输出**金额**，而不是 True/False。

⭐ 核心纪律：**规则只有一份**。本文件不重写任何入场/离场条件，只做形状翻译：
    entry_fn 出信号 → 把现金全部买入（满仓）
    exit_fn 给出原因 → 把持仓全部卖出（清仓）
规则仍然只写在 quant/strategies/*.py 里，改一处两边同时生效。
（反面做法是手抄一份规则进 portfolios/ → 两份实现迟早漂移，回测开始骗人。）

与单标的引擎（engine.py）的三处口径差异（必须知道，不是 bug）：
1. **成交价**：engine 用 T+1 **开盘价**，组合引擎用 T+1 **收盘/净值**。
   场外基金本来一天只有一个净值（open=close=当日净值），所以对基金而言两边同价；
   对个股/指数会有差别，同一策略两边数字不会完全相同，别当成 bug。
2. **预热段**：✅ 2026-07-28 已对齐。曾经的差异是组合引擎的 ctx.hist 从回测起点才
   开始，开头几周指标算不出来 → 信号被静默漏掉（bottom_reversal 因此漏掉 2018-07-09
   的入场，同标的同规则两边跑出 +49.5% vs +51.2%）。现在 hist 从"全员就绪日"起切、
   每天切到当天（quant/portfolio.py 的 warm），两边指标记忆长度一致。
   **给配方留的功课**：想让预热段真的够长，配方里的 data_start 要往前留够
   （如 bottom_reversal_fund 写 "20110101"），否则取数就没那么多历史可暖机。
3. **冷却期**：engine 的 cooldown_days（卖出后冷却，防同一波下跌反复进场）属于
   引擎纪律，这里按同样默认值 10 复刻；改这个参数会让两边不可比。
"""
from dataclasses import replace

import pandas as pd

from quant.engine import Position
from quant.exits import ExitSpec, adjust_for_fund


def _today_signal(entry_fn, px):
    """在"截至今天"的净值序列上算入场信号，取最后一天的值（NaN 当 False）。

    只传 close 一列：场外基金没有开高低收。策略若依赖 OHLC/成交量，这里会
    KeyError——那种策略本来就没法用基金净值跑，明确报错好过悄悄给个假信号。
    """
    df = px.rename("close").to_frame()
    try:
        sig = entry_fn(df)
    except KeyError as e:
        raise ValueError(f"该策略需要 {e} 列，但基金净值只有 close 一列 → 无法适配") from e
    if not isinstance(sig, pd.Series):
        sig = pd.Series(sig, index=df.index)
    val = sig.iloc[-1]
    return bool(val) if pd.notna(val) else False


def strategy_as_portfolio(strategy_name, asset=None, cooldown_days=10, fund_mode=True):
    """把 quant/strategies/ 里的择时策略包成组合决策函数（满仓进 / 清仓出）。

    参数：
        strategy_name: 策略注册名（如 "bottom_reversal"）——规则从注册表取，不复制
        asset:         对哪只标的择时；None = 组合里唯一那只
        cooldown_days: 卖出后冷却交易日数，与 engine.run_backtest 默认值一致
        fund_mode:     True = 走基金口径（ExitSpec 的 min_hold 自动提到 5 个交易日，
                       覆盖 7 个自然日 1.5% 惩罚性赎回费，见 Knowledge/funds.md）
    """
    from quant.strategies import REGISTRY          # 延迟 import：避免注册表循环依赖
    if strategy_name not in REGISTRY:
        raise KeyError(f"策略 {strategy_name!r} 不在 quant/strategies 注册表里："
                       f"{sorted(REGISTRY)}")
    strat = REGISTRY[strategy_name]
    rule = adjust_for_fund(strat.exit, "fund") if fund_mode else strat.exit
    exit_fn = rule.to_fn() if isinstance(rule, ExitSpec) else rule
    exit_desc = rule.describe() if isinstance(rule, ExitSpec) \
        else getattr(rule, "__name__", "自定义离场")

    st = {}

    def decide(ctx):
        if asset is None and len(ctx.names) != 1:
            raise ValueError(f"择时适配器默认只管一只标的，但组合有 {ctx.names}；"
                             f"请用 asset= 指定对哪只择时")
        name = asset or ctx.names[0]
        if ctx.i == 0:                              # 每次回测重置状态（工厂函数会被复用）
            st.clear()
            st.update(pos=None, cool=0)

        held, close = float(ctx.values[name]), float(ctx.prices[name])
        # —— 与引擎对账：成交发生在引擎里，这里只根据"现在有没有持仓"同步状态 ——
        if held <= 1e-9 and st["pos"] is not None:          # 昨天的卖单已成交
            st.update(pos=None, cool=cooldown_days)
        if held > 1e-9 and st["pos"] is None:               # 昨天的买单已成交
            st["pos"] = Position(entry_price=close, entry_date=ctx.date,
                                 hold_days=0, peak_close=close)

        pos = st["pos"]
        if pos is not None:                         # 持仓中：只判离场（与 engine 同顺序）
            pos.hold_days += 1
            pos.peak_close = max(pos.peak_close, close)
            hist = ctx.hist[name].rename("close").to_frame()
            reason = exit_fn(pos, pd.Series({"close": close}), hist)
            # 清仓要**故意多下单**（×2）：卖单在 T+1 才成交，若按今天的市值下单，
            # 明天涨了就会剩一点尾巴卖不掉，持仓清不干净 → 离场规则第二天又触发一次
            # （首版就踩了这个坑：日志里出现 -46 元、-20 元、0 元的碎单）。
            # 引擎对卖单有"不超过持仓"的截断，多下单不会卖空，所以这是清仓的正确写法。
            return {name: -held * 2} if reason is not None else None
        if st["cool"] > 0:                          # 冷却期：不看信号（与 engine 一致）
            st["cool"] -= 1
            return None
        if _today_signal(strat.entry_fn, ctx.hist[name]) and ctx.cash > 1:
            return {name: ctx.cash}                 # 满仓买入（引擎会按现金截断并扣成本）
        return None

    decide.desc = (f"择时策略「{strategy_name}」适配版：入场信号→满仓买入，"
                   f"{exit_desc}→清仓，卖后冷却 {cooldown_days} 日")
    decide.factory = strategy_as_portfolio
    decide.params = {"strategy_name": strategy_name, "asset": asset,
                     "cooldown_days": cooldown_days, "fund_mode": fund_mode}
    return decide


__all__ = ["strategy_as_portfolio"]
