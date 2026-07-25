# -*- coding: utf-8 -*-
"""
zhihu_strategy1_oversold.py — 知乎抄底策略 v2：忠于"短期超跌博反弹"原意的回测（计划 06 补充）

背景：v1（zhihu_strategy1_verify.py）的 Part A 被指出方法论缺陷——
"拿着作者的结论去历史里找匹配"：窗口里随便找一个低点（比如 -3.2% 回撤）就算
"验证了规律"，但这种小回撤历史上一年出现好几次，毫无区分度。

作者策略的【原意】是：短期内超跌（恐慌性急跌）→ 有反弹需求 → 抄进去吃一波短弹就走。
所以 v2 做两件事：

  Part 1【质疑的量化证明】统计"回撤 ≥3%"这种信号每年出现多少次，
        证明它太常见、不是有效信号；真正的"短期超跌"（10 日跌 7%+）每年才 0-2 次。

  Part 2【超跌反弹策略回测】严格按原意的规则化：
        - 买入：N 日收益率 ≤ -X%（短期急跌、恐慌抛售）→ 次日开盘买
        - 卖出：反弹 +TP% 止盈（吃的就是"短期需求"），或 20 个交易日没反弹就离场
        - 是否止损：作者原话"指数基金不会退市，等就完了"——基准版不止损，
          另报一个带止损的对照版，看哪种更诚实

用法：python zhihu_strategy1_oversold.py
"""

import sys

import pandas as pd

from fetch_data import fetch_daily

sys.stdout.reconfigure(encoding="utf-8")

START = "2018-07-01"   # 与 v1 回测同一区间，结果可比
COST = 0.001           # 买卖双边成本（ETF 无印花税，约 0.1%）


def cross_down(cond):
    """条件从 False 变 True 的"首日"（避免连续满足时天天发信号）。"""
    return cond & ~cond.shift(1, fill_value=False)


# ------------------------------------------------------------
# Part 1：证明"-3% 回撤"太常见，不是有效信号
# ------------------------------------------------------------
def part1_signal_frequency(df, name):
    """统计三类"跌法"每年各出现几次（按首次跌破计）。"""
    close = df["close"]
    dd60 = close / close.rolling(60).max() - 1          # 距 60 日高点的回撤
    events = pd.DataFrame({
        "60日高点回撤≥3%": cross_down(dd60 <= -0.03),
        "60日高点回撤≥8%": cross_down(dd60 <= -0.08),
        "10日内急跌≥7%": cross_down(close.pct_change(10) <= -0.07),
    })
    yearly = events.loc["2019":].groupby(events.loc["2019":].index.year).sum()
    print(f"\n{'=' * 70}\nPart 1：{name}——三种'跌法'每年各出现几次？\n{'=' * 70}")
    print(yearly.to_string())
    n_years = len(yearly)
    for col in yearly.columns:
        print(f"  {col}：年均 {yearly[col].sum() / n_years:.1f} 次")


# ------------------------------------------------------------
# Part 2：超跌反弹策略回测
# ------------------------------------------------------------
def run_backtest(df, entry_signal, take_profit=0.05, stop_loss=None,
                 max_hold=20, cost=COST, cooldown_days=10):
    """通用无未来函数回测：T 日收盘出信号 → T+1 开盘成交。

    entry_signal：布尔 Series（True = 当天收盘出现买入信号）
    卖出：止盈 +take_profit / 止损 -stop_loss（None=不止损）/ 超期 max_hold 个交易日
    """
    sig = entry_signal.fillna(False)
    trades, equity = [], []
    cash, shares, entry_price, entry_date, hold = 1.0, 0.0, None, None, 0
    entry_cash = None
    pending_buy, pending_sell = False, None
    cooldown = 0

    for i, (date, row) in enumerate(df.iterrows()):
        # —— 开盘处理昨天的信号 ——
        if pending_buy and shares == 0:
            entry_cash = cash
            shares = cash * (1 - cost) / row["open"]
            cash, entry_price, entry_date, hold = 0.0, row["open"], date, 0
            pending_buy = False
        elif pending_sell and shares > 0:
            cash = shares * row["open"] * (1 - cost)
            trades.append({
                "买入日": entry_date.strftime("%Y-%m-%d"),
                "卖出日": date.strftime("%Y-%m-%d"),
                "持有交易日": hold,
                "收益率": cash / entry_cash - 1,
                "卖出原因": pending_sell,
            })
            shares, cooldown = 0.0, cooldown_days
            pending_sell = None

        # —— 收盘出信号（只用当天及以前的数据）——
        if shares > 0:
            hold += 1
            if row["close"] >= entry_price * (1 + take_profit):
                pending_sell = "止盈"
            elif stop_loss is not None and row["close"] <= entry_price * (1 - stop_loss):
                pending_sell = "止损"
            elif hold >= max_hold:
                pending_sell = "超期"
        elif cooldown > 0:
            cooldown -= 1
        elif sig.iloc[i]:
            pending_buy = True

        equity.append(cash + shares * row["close"])

    return pd.DataFrame(trades), pd.Series(equity, index=df.index)


def summarize(trades, eq, df, label, show_trades=True):
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1
    ann = (1 + total) ** (1 / n_years) - 1 if total > -1 else -1
    mdd = (eq / eq.cummax() - 1).min()
    bh = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    print(f"\n--- {label} ---")
    if len(trades):
        win = (trades["收益率"] > 0).mean()
        avg_win = trades.loc[trades["收益率"] > 0, "收益率"].mean()
        avg_loss = trades.loc[trades["收益率"] <= 0, "收益率"].mean()
        print(f"交易次数：{len(trades)}   胜率：{win:.0%}   平均每笔：{trades['收益率'].mean():.1%}"
              f"（平均盈 {avg_win:.1%} / 平均亏 {avg_loss:.1%}）")
    else:
        print("无交易")
    print(f"总收益：{total:.1%}   年化：{ann:.1%}   最大回撤：{mdd:.1%}   （买入持有：{bh:.1%}）")
    if show_trades and len(trades):
        t = trades.copy()
        t["收益率"] = (t["收益率"] * 100).round(1).astype(str) + "%"
        print(t.to_string(index=False))
    return ann


def part2(df, name):
    bt = df.loc[START:]
    close = bt["close"]

    print(f"\n{'=' * 70}\nPart 2：{name}——'短期超跌博反弹'规则化回测\n{'=' * 70}")

    # 基准信号：10 日收益率 ≤ -7%（短期急跌、恐慌）
    sig = cross_down(close.pct_change(10) <= -0.07)
    print(f"信号出现次数：{sig.sum()} 次")

    # 版本 A：忠于作者——不止损，反弹 +5% 止盈，20 日没反弹离场
    trades, eq = run_backtest(bt, sig, take_profit=0.05, stop_loss=None, max_hold=20)
    summarize(trades, eq, bt, f"{name} 版本A：不止损，+5%止盈/20日离场")

    # 版本 B：带 -7% 止损的对照
    trades, eq = run_backtest(bt, sig, take_profit=0.05, stop_loss=0.07, max_hold=20)
    summarize(trades, eq, bt, f"{name} 版本B：-7%止损，+5%止盈/20日离场", show_trades=False)


def param_sweep(df, name):
    """参数扰动：急跌窗口 N、跌幅阈值 X、止盈 TP 各换几档（版本A 不止损）。"""
    bt = df.loc[START:]
    close = bt["close"]
    n_years = (bt.index[-1] - bt.index[0]).days / 365.25
    print(f"\n--- {name} 参数扰动（年化收益，版本A 规则）---")
    for tp in (0.03, 0.05, 0.08):
        print(f"止盈 {tp:.0%}：")
        print("  急跌定义\\阈值 |   -5%  |   -7%  |  -10%  ")
        for n in (5, 10, 20):
            cells = []
            for th in (0.05, 0.07, 0.10):
                sig = cross_down(close.pct_change(n) <= -th)
                _, eq = run_backtest(bt, sig, take_profit=tp, stop_loss=None, max_hold=20)
                total = eq.iloc[-1] - 1
                ann = (1 + total) ** (1 / n_years) - 1 if total > -1 else -1
                cells.append(f"{ann:6.1%}")
            print(f"   {n:2}日收益率     | " + " | ".join(cells))


def main():
    for symbol, name in [("000001", "上证指数"), ("000300", "沪深300")]:
        df = fetch_daily("idx", symbol, start="20180101")
        df = df.set_index(pd.to_datetime(df["date"])).sort_index()
        part1_signal_frequency(df, name)
        part2(df, name)
        param_sweep(df, name)


if __name__ == "__main__":
    main()
