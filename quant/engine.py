# -*- coding: utf-8 -*-
"""
quant/engine.py — ④ 引擎层：全项目唯一的事件循环（回测发动机）

教学要点（这层为什么"不变"）：
回测的本质是"模拟时间一天天流过，按规则记账"。这个循环里的每一条规则
（T+1 次日成交、成本扣除、持仓天数、峰值跟踪）都是【纪律】，不该随策略变化——
策略能决定的只有两件事：哪天买（entry_fn）、哪天卖（exit_fn）。
所以引擎把这两个决策点做成"插槽"，策略插上来就能跑，引擎本身一行不用改。

无未来函数的两道硬防线：
1. T 日收盘算出信号 → 记为 pending → T+1 开盘才成交（引擎强制，无可选项）
2. 自定义离场函数只收到 hist 历史切片（截至当日的数据），
   物理上拿不到未来数据——契约级防护，不靠自觉
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Position:
    """当前持仓状态（引擎每天维护后交给 exit_fn 判断）。
    peak_close：持仓期间的最高收盘价，移动止盈的"锚"。
    """
    entry_price: float
    entry_date: pd.Timestamp
    hold_days: int
    peak_close: float


def _as_bool_series(sig, df):
    """把 entry_fn 的返回值统一成与 df 等长的布尔 Series（NaN 一律当 False）。"""
    if not isinstance(sig, pd.Series):
        sig = pd.Series(np.asarray(sig), index=df.index)
    if len(sig) != len(df):
        raise ValueError(f"entry_fn 返回长度 {len(sig)} 与数据行数 {len(df)} 不一致")
    if not sig.index.equals(df.index):
        sig = sig.reindex(df.index)
    return sig.fillna(False).astype(bool)


def run_backtest(df, entry_fn, exit_fn, start=None, cost=0.001, cooldown_days=10):
    """单标的、全仓进出、T+1 低频回测。

    参数：
        df:        date 索引 + open/high/low/close/volume（含 start 之前的预热段，
                   指标需要预热段"暖机"，信号在完整 df 上算完再切片，与 v3 口径一致）
        entry_fn:  入场函数，df -> 与 df 等长的布尔 Series（True = 当天收盘出信号）
        exit_fn:   离场函数，(position, row, hist) -> 离场原因字符串 或 None
        start:     回测起点（如 "2018-07-01"）；None = 从 df 第一行开始
        cost:      单边成本（买卖各扣一次；双边 0.1% 就传 0.001）
        cooldown_days: 卖出后冷却天数，防止同一波下跌反复触发买入

    返回：(trades DataFrame, equity 净值 Series)
        单笔收益率 = 卖出后现金 / 买入前现金 − 1（别从持仓反推，会重复扣成本）
    """
    if start is not None:
        sig_full = _as_bool_series(entry_fn(df), df)
        bt = df.loc[pd.Timestamp(start):]
        sig = sig_full.loc[bt.index]
    else:
        bt = df
        sig = _as_bool_series(entry_fn(df), df)
    if len(bt) == 0:
        raise ValueError(f"回测区间为空：start={start!r} 之后没有数据")

    sig_v = sig.values
    trades, equity = [], []
    cash, shares, pos, entry_cash = 1.0, 0.0, None, None
    pending_buy, pending_sell, cooldown = False, None, 0

    for i, (date, row) in enumerate(bt.iterrows()):
        # —— 开盘：执行昨天收盘定下的买卖（T 日信号 → T+1 开盘成交）——
        if pending_buy and shares == 0:
            entry_cash = cash
            shares = cash * (1 - cost) / row["open"]
            cash = 0.0
            pos = Position(entry_price=row["open"], entry_date=date,
                           hold_days=0, peak_close=row["close"])
            pending_buy = False
        elif pending_sell and shares > 0:
            cash = shares * row["open"] * (1 - cost)
            trades.append({
                "买入日": pos.entry_date.strftime("%Y-%m-%d"),
                "卖出日": date.strftime("%Y-%m-%d"),
                "持有交易日": pos.hold_days,
                "收益率": cash / entry_cash - 1,
                "卖出原因": pending_sell,
            })
            shares, cooldown = 0.0, cooldown_days
            pos, pending_sell = None, None

        # —— 收盘：只用当天及以前的数据做决策 ——
        if shares > 0:
            pos.hold_days += 1
            pos.peak_close = max(pos.peak_close, row["close"])
            hist = df.loc[:date]          # 截至当日的切片：物理上不含未来数据
            reason = exit_fn(pos, row, hist)
            if reason is not None:
                pending_sell = reason
        elif cooldown > 0:
            cooldown -= 1
        elif sig_v[i]:
            pending_buy = True

        equity.append(cash + shares * row["close"])

    # 期末仍持仓：按最后收盘估值，不强制平仓（trades 里也不会有这笔）
    cols = ["买入日", "卖出日", "持有交易日", "收益率", "卖出原因"]
    return pd.DataFrame(trades, columns=cols), pd.Series(equity, index=bt.index)


def assert_no_lookahead(entry_fn, df):
    """因果性门禁 ⭐：前缀不变性测试，signals.py 每个新信号必须过这一关。

    原理：如果信号计算只用了"当天及以前"的数据，那么把 df 截断到第 k 天重算，
    前 k 个信号必须和全量计算的前 k 个【逐日一致】。shift(-1)、全样本归一化
    这类"偷看未来"的 bug，截断后末尾几天的信号一定会变，当场现形。
    """
    full = _as_bool_series(entry_fn(df), df)
    n = len(df)
    ks = sorted({max(2, int(n * f)) for f in (0.25, 0.5, 0.75)} | {n - 1})
    for k in ks:
        trunc = _as_bool_series(entry_fn(df.iloc[:k]), df.iloc[:k])
        if not (trunc.values == full.values[:k]).all():
            bad = int(np.nonzero(trunc.values != full.values[:k])[0][0])
            raise AssertionError(
                f"未来函数警报：df 截断到 {k} 行重算后，"
                f"{df.index[bad]:%Y-%m-%d}（第 {bad} 行）的信号从 "
                f"{full.values[bad]} 变成 {trunc.values[bad]}。"
                f"常见元凶：shift(-1)、无窗口的全列统计、全样本归一化。")
    return True
