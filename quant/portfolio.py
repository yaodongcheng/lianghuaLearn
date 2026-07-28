# -*- coding: utf-8 -*-
"""
quant/portfolio.py — ④ 引擎层：多标的组合回测（与 engine.py 平级，纪律同样写死在引擎里）

两个引擎回答的是两个不同的问题：
    engine.py    择时：一只标的"何时全仓进、何时全仓出"
    portfolio.py 配置：几只标的"钱怎么分、什么时候重新分"

引擎负责的纪律（策略无权改）：
- T 日收盘拿到状态 → 策略给出订单 → **T+1 收盘/净值成交**
  （场外基金一天一价，T 日提交按 T+1 净值成交；场内 ETF 的 T+1 执行也等价）
- 成交额按固定比例双边扣成本（与 engine.py 同口径）
- 卖单先执行回笼现金，再执行买单；买单受现金约束、卖单受持仓约束（见 portfolio_fill.py）
- 逐日记账：总市值、各标的权重、每次调仓的方向和金额
- **逐日分腿记损益**（2026-07-28 加）：每天记"昨日份数 × 今日净值变化"，并在每次
  持仓变动时把"上次调仓到这次之间各腿赚/亏了多少元"写进成交日志。为什么放引擎里而
  不事后算：动态持仓（权重漂移+再平衡削减）靠权重反推份数必带误差。用法见
  quant/attribution.py

策略负责的决策：decide_fn(ctx) -> {标的: 带符号金额}（见 quant/rebalance.py）

防未来函数（结构性保证，不靠自觉）：
- ctx.hist 只切到今天，策略连未来数据的引用都拿不到
- 订单永远在下一个交易日成交，成交价是决策时未知的价
- 多标的日期对齐用 outer join + ffill（向前填充=用最近已知净值估值，只朝过去填）
"""

import pandas as pd

# 取数/对齐/快照在 portfolio_data.py（本文件只放"钱怎么动"的循环），一并转出给老调用方
from quant.portfolio_data import PortfolioContext, align_prices, load_portfolio_navs
from quant.portfolio_fill import fill_orders     # 订单撮合（截断/成本）在那边

__all__ = ["run_portfolio_backtest", "load_portfolio_navs", "align_prices",
           "PortfolioContext"]


def run_portfolio_backtest(nav_map, decide_fn, start=None, cost=0.001,
                           initial_cash=10000.0):
    """组合回测事件循环：T 日收盘决策 → T+1 收盘/净值成交。

    参数：
        nav_map:      {名称: DataFrame(date 索引, close 列)}，基金净值或价格
        decide_fn:    决策函数 ctx -> {名称: 带符号金额}（见 quant/rebalance.py）
        start:        回测起点（None = 所有成分都有数据的首日）
        cost:         单边成本率（买、卖各扣一次，与 engine.py 同口径）
        initial_cash: 初始资金（元）

    返回 (equity, weights, log)：
        equity:  组合每日总资产 Series（date 索引；attrs["总成本"] 附总手续费）
        weights: 各标的每日权重 DataFrame（列=标的）
                 attrs 附归因原料：shares/cash/prices/pnl（见文件末尾注释）
        log:     成交日志 DataFrame（日期/成交总额/成本/各标的带符号成交金额
                 /各标的本段持有损益「贡献-X」）
    """
    names = list(nav_map)
    px, first_full = align_prices(nav_map)
    bt_start = pd.Timestamp(start) if start is not None else first_full
    if bt_start < first_full:
        # 起点早于最晚上市的成分 → 组合根本不可能成立，明确报错而不是静默晚开始
        raise ValueError(f"回测起点 {bt_start:%Y-%m-%d} 早于全部成分就绪日 "
                         f"{first_full:%Y-%m-%d}（最后上市的成分这天才有数据）")
    bt = px.loc[bt_start:, names]
    if len(bt) < 2:
        raise ValueError("回测区间不足 2 个交易日")
    # 指标预热段：ctx.hist 从"全员都有数据的首日"起切，而不是从回测起点起切。
    # 为什么必须这样（2026-07-28 查出的口径 bug）：策略要算 RSI6/MA20 这类指标，头几行
    # 算不出来。若 hist 只给回测起点之后的数据，回测开头几周的信号会被**静默漏掉**——
    # bottom_reversal 就因此漏掉 2018-07-09 的入场信号，同一规则在单标的引擎（它本来
    # 就多取半年数据暖机）跑 +49.5%、这里跑 +51.2%，两边对不上。
    # 这不引入未来函数：warm 是全历史矩阵，但每天只切到当天（下面 .loc[:date]）。
    # 起点用 first_full 而非 px 首行：更早的行里成分是 NaN，ffill 填不了最前面的空洞。
    warm = px.loc[first_full:, names]

    shares = {n: 0.0 for n in names}
    cash = float(initial_cash)
    total_cost = 0.0
    equity, weight_rows, log = [], [], []
    share_rows, cash_rows, pnl_rows = [], [], []   # 归因用：每日收盘份数/现金/分腿损益
    seg = {n: 0.0 for n in names}   # 自上次成交以来各腿累计损益（成交时写进日志再清零）
    prev = None                     # 昨日收盘的 (份数, 净值)，算今日损益要用
    pending = None            # 昨天的订单，今天收盘成交（T+1 纪律）

    for i, (date, price) in enumerate(bt.iterrows()):
        # ---------- ⓪ 今日分腿损益 = 昨日收盘份数 × 今日净值变化 ----------
        # 必须在执行订单**之前**算：成交按当日净值成交，买卖本身不产生盈亏（只产生
        # 手续费），"今天赚了多少"只取决于昨天手上拿着多少份。顺序颠倒的话，今天刚
        # 买进的份数会被算上一段不属于它的涨跌。
        day_pnl = {n: prev[0][n] * (price[n] - prev[1][n]) for n in names} \
            if prev is not None else {n: 0.0 for n in names}
        pnl_rows.append(day_pnl)
        for n in names:
            seg[n] += day_pnl[n]

        # ---------- ① 执行昨天的订单（T+1 成交，成交价是决策时不知道的今日价）----------
        if pending:
            # 截断规则（不许透支/裸卖空）在 portfolio_fill.py，shares 被原地更新
            traded, fee, cash = fill_orders(pending, names, price, shares, cash, cost)
            if traded:
                total_cost += fee
                # 每次持仓变动都留一份"这段时间钱是谁赚的"的快照：
                # 贡献-X = 上一次成交日（不含那天）到今天（含）之间 X 的持有损益
                log.append({"日期": date,
                            "成交总额": sum(abs(v) for v in traded.values()),
                            "成本": fee,
                            **{f"调仓-{n}": traded.get(n, 0.0) for n in names},
                            **{f"贡献-{n}": seg[n] for n in names}})
                seg = {n: 0.0 for n in names}    # 段落结束，重新起算
            pending = None

        # ---------- ② 收盘记账 ----------
        values = pd.Series({n: shares[n] * price[n] for n in names})
        total = values.sum() + cash
        equity.append(total)
        weight_rows.append(values / total)
        share_rows.append(dict(shares))         # 收益归因要精确份数，不能用权重反推
        cash_rows.append(cash)

        # ---------- ③ 今日决策（只看今天及以前；最后一天不再下单，因为没有 T+1 了）----------
        if i < len(bt) - 1:
            ctx = PortfolioContext(date=date, names=names, prices=price,
                                   hist=warm.loc[:date], shares=dict(shares),
                                   cash=cash, values=values, total=total,
                                   weights=values / total, i=i)
            orders = decide_fn(ctx) or {}
            unknown = set(orders) - set(names)
            if unknown:
                raise ValueError(f"决策函数返回了不在组合里的标的：{sorted(unknown)}")
            pending = {n: float(v) for n, v in orders.items() if abs(float(v)) > 1e-9}

        prev = (dict(shares), price.copy())     # 今日收盘状态 → 明天算损益的基准

    eq = pd.Series(equity, index=bt.index)
    weights = pd.DataFrame(weight_rows, index=bt.index)
    log_df = pd.DataFrame(log, columns=["日期", "成交总额", "成本"]
                          + [f"调仓-{n}" for n in names]
                          + [f"贡献-{n}" for n in names])
    eq.attrs["总成本"] = total_cost      # 附在净值曲线上，报告层取用
    eq.attrs["建仓日"] = log_df["日期"].iloc[0] if len(log_df) else None
    log_df.attrs["贡献口径"] = ("贡献-X = 上一次成交日（不含）到本行日期（含）之间，"
                                "X 这条腿的持有损益（元），与当天买卖金额无关；"
                                "最后一次成交日之后的尾段不在表里，看 attribution 分段表")
    # 归因原料挂在 weights 上（不改返回值签名，老调用方无感）：每日收盘份数 shares、
    # 现金 cash、对齐后净值 prices、各成分当日持有损益 pnl（引擎实时记的账，非事后反推）
    weights.attrs["shares"] = pd.DataFrame(share_rows, index=bt.index)[names]
    weights.attrs["cash"] = pd.Series(cash_rows, index=bt.index)
    weights.attrs["prices"] = bt.copy()
    weights.attrs["pnl"] = pd.DataFrame(pnl_rows, index=bt.index)[names]
    return eq, weights, log_df
