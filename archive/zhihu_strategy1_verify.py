# -*- coding: utf-8 -*-
"""
zhihu_strategy1_verify.py — 验证知乎"每年 2-4 月抄底指数"策略（计划 06）

策略原文（Knowledge/zhihu/吃超跌恐慌修复策略.md，原名 strategy1.md）的核心声称：
  1. 每年上半年 2-4 月都有一次大跌，形成"相对底部"
  2. 抄底后一波反弹 15-20 个点，一年做 2-3 次，年化 30-40%
  3. 低点清单：19年2月初、20年3月下旬、21年3月底、22年3月、
     23年3月、24年2月、25年4月、26年4月

本脚本分两部分：
  Part A【事实核查】回头看：每年 2-4 月窗口里最深跌了多少、之后反弹了多少。
        —— 注意：这是"事后视角"，用来验证规律是否存在，不能直接当收益。
  Part B【规则回测】把"相对底部"翻译成明确的、无未来函数的买卖规则：
        - 买入：收盘价跌破近 60 日高点 X% → 次日开盘价买（当天收盘才知道跌了多少）
        - 卖出：盈利 ≥ TP% 止盈，或持仓满 60 个交易日离场 → 次日开盘价卖
        - 同一时间最多一笔仓位，空仓期间不产生收益
        再对参数做扰动测试，看结论稳不稳（防过拟合）。

用法：python zhihu_strategy1_verify.py
"""

import sys
from pathlib import Path

import pandas as pd

from fetch_data import fetch_daily

sys.stdout.reconfigure(encoding="utf-8")

YEARS = range(2019, 2027)          # 2026 只有前 7 个月数据
WINDOW_H1 = ("02-01", "04-30")     # 作者说的"上半年 2-4 月"
WINDOW_H2 = ("07-01", "11-30")     # 作者说"下半年也有一次"，考察 7-11 月
PRIOR_HIGH_DAYS = 60               # "相对底部"的参照：近 60 个交易日高点
REBOUND_DAYS = 60                  # 抄底后给反弹的时间：60 个交易日（约 3 个月）


# ------------------------------------------------------------
# Part A：事实核查
# ------------------------------------------------------------
def check_window(df, year, win, label):
    """核查某年某个时间窗口：最深回撤 + 之后 60 个交易日内的最大反弹。

    教学说明：回撤的参照高点取"窗口最低点之前 60 个交易日的最高收盘价"，
    因为"相对底部"一定是相对之前的高点而言的。
    """
    lo, hi = f"{year}-{win[0]}", f"{year}-{win[1]}"
    win_df = df.loc[lo:hi]
    if len(win_df) < 5:
        return None

    low_date = win_df["close"].idxmin()          # 窗口内最低收盘价
    low_price = win_df["close"].min()

    # 最低点之前 60 个交易日的最高收盘价（含当天）
    pos = df.index.get_loc(low_date)
    prior = df.iloc[max(0, pos - PRIOR_HIGH_DAYS):pos + 1]
    prior_high = prior["close"].max()
    prior_high_date = prior["close"].idxmax()

    # 最低点之后 60 个交易日内的最高收盘价
    after = df.iloc[pos:pos + REBOUND_DAYS + 1]
    rebound_high = after["close"].max()
    rebound_date = after["close"].idxmax()

    return {
        "时段": label,
        "窗口最低日": low_date.strftime("%m-%d"),
        "前高日期": prior_high_date.strftime("%Y-%m-%d"),
        "回撤幅度": low_price / prior_high - 1,
        "之后最大反弹": rebound_high / low_price - 1,
        "反弹到位日": rebound_date.strftime("%Y-%m-%d"),
        "反弹耗时(交易日)": df.index.get_loc(rebound_date) - pos,
    }


def part_a(df, name):
    print(f"\n{'=' * 78}\nPart A 事实核查：{name}（回头看各窗口的回撤与反弹）\n{'=' * 78}")
    rows = []
    for y in YEARS:
        r1 = check_window(df, y, WINDOW_H1, f"{y} 上半年(2-4月)")
        r2 = check_window(df, y, WINDOW_H2, f"{y} 下半年(7-11月)")
        rows += [r for r in (r1, r2) if r]
    out = pd.DataFrame(rows)
    out["回撤幅度"] = (out["回撤幅度"] * 100).round(1).astype(str) + "%"
    out["之后最大反弹"] = (out["之后最大反弹"] * 100).round(1).astype(str) + "%"
    print(out.to_string(index=False))
    return rows


# ------------------------------------------------------------
# Part B：规则化回测
# ------------------------------------------------------------
def run_backtest(df, dd_threshold=0.08, take_profit=0.15,
                 max_hold_days=60, cost=0.001, prior_days=60):
    """无未来函数的抄底回测。

    规则（全部满足"当天收盘出信号、次日开盘成交"）：
      买入信号：当日收盘价 / 近 prior_days 日最高收盘 - 1 <= -dd_threshold
                （且昨天还没跌破 → 只在"刚跌破"那天触发一次，避免天天发信号）
      卖出信号：收盘价较买入价盈利 >= take_profit（止盈）
                或持仓满 max_hold_days 个交易日（超期离场）
      成本：买卖双边合计 cost（ETF 无印花税，约 0.1%）

    返回：交易明细 DataFrame + 每日净值 Series
    """
    close = df["close"]
    rolling_high = close.rolling(prior_days).max()
    drawdown = close / rolling_high - 1
    # 刚跌破阈值的瞬间（昨天还在阈值之上，今天破）——这就是规则化的"相对底部出现"
    trigger = (drawdown <= -dd_threshold) & (drawdown.shift(1) > -dd_threshold)

    trades, equity = [], []
    cash, shares, entry_price, entry_date, hold_days = 1.0, 0.0, None, None, 0
    entry_cash = None          # 买入前的现金，用于算单笔收益率
    pending_buy, pending_sell = False, False
    cooldown = 0  # 卖出后冷静 10 个交易日再允许下次买入，避免刚卖又追

    for i, (date, row) in enumerate(df.iterrows()):
        # —— 开盘处理昨天的信号（T 日收盘信号 → T+1 开盘成交）——
        if pending_buy and shares == 0:
            entry_cash = cash
            shares = cash * (1 - cost) / row["open"]
            cash, entry_price, entry_date, hold_days = 0.0, row["open"], date, 0
            pending_buy = False
        elif pending_sell and shares > 0:
            cash = shares * row["open"] * (1 - cost)
            trades.append({
                "买入日": entry_date.strftime("%Y-%m-%d"),
                "卖出日": date.strftime("%Y-%m-%d"),
                "持有交易日": hold_days,
                "收益率": cash / entry_cash - 1,
                "卖出原因": pending_sell,
            })
            shares, cooldown = 0.0, 10
            pending_sell = False

        # —— 收盘出信号（只用当天及以前的数据）——
        if shares > 0:
            hold_days += 1
            if row["close"] >= entry_price * (1 + take_profit):
                pending_sell = "止盈"
            elif hold_days >= max_hold_days:
                pending_sell = "超期"
        elif cooldown > 0:
            cooldown -= 1
        elif trigger.iloc[i] and not pd.isna(trigger.iloc[i]):
            pending_buy = True

        equity.append(cash + shares * row["close"])

    # 收尾：还有持仓就按最后收盘价估值（不算强平，只记账）
    eq = pd.Series(equity, index=df.index)
    return pd.DataFrame(trades), eq


def summarize(trades, eq, df, label):
    """打印回测概要。年化口径：全区间（含空仓时间），见 Knowledge/metrics.md。"""
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    total_ret = eq.iloc[-1] / eq.iloc[0] - 1
    ann = (1 + total_ret) ** (1 / n_years) - 1 if total_ret > -1 else -1
    mdd = (eq / eq.cummax() - 1).min()
    bh = df["close"].iloc[-1] / df["close"].iloc[0] - 1   # 同期买入持有

    win = (trades["收益率"] > 0).mean() if len(trades) else float("nan")
    print(f"\n--- {label} ---")
    print(f"交易次数：{len(trades)}   胜率：{win:.0%}   "
          f"平均每笔：{trades['收益率'].mean():.1%}" if len(trades) else "无交易")
    print(f"总收益：{total_ret:.1%}   年化：{ann:.1%}   最大回撤：{mdd:.1%}")
    print(f"（对照）同期买入持有：{bh:.1%}")
    if len(trades):
        t = trades.copy()
        t["收益率"] = (t["收益率"] * 100).round(1).astype(str) + "%"
        print(t.to_string(index=False))


def part_b(df, name):
    print(f"\n{'=' * 78}\nPart B 规则化回测：{name}"
          f"（跌破60日高点8%买，+15%止盈/60日离场，成本0.1%）\n{'=' * 78}")
    # 从 2019 年开始回测（2018 年数据留给 60 日高点窗口预热）
    bt = df.loc["2018-07-01":]
    trades, eq = run_backtest(bt)
    summarize(trades, eq, bt, f"{name} 基准参数")
    return trades, eq, bt


def param_sweep(df, name):
    """参数扰动测试：阈值和止盈各换几档，看结论是否稳定（防过拟合）。"""
    print(f"\n--- {name} 参数扰动（年化收益）---")
    bt = df.loc["2018-07-01":]
    n_years = (bt.index[-1] - bt.index[0]).days / 365.25
    header = "回撤阈值\\止盈 | " + " | ".join(f"  {tp:.0%}  " for tp in (0.10, 0.15, 0.20))
    print(header)
    for th in (0.05, 0.08, 0.10, 0.12):
        cells = []
        for tp in (0.10, 0.15, 0.20):
            trades, eq = run_backtest(bt, dd_threshold=th, take_profit=tp)
            total = eq.iloc[-1] - 1
            ann = (1 + total) ** (1 / n_years) - 1 if total > -1 else -1
            cells.append(f"{ann:6.1%}")
        print(f"     {th:5.0%}      | " + " | ".join(cells))


# ------------------------------------------------------------
def main():
    for symbol, name in [("000001", "上证指数"), ("000300", "沪深300")]:
        df = fetch_daily("idx", symbol, start="20180101")
        df = df.set_index(pd.to_datetime(df["date"])).sort_index()
        part_a(df, name)
        part_b(df, name)
        param_sweep(df, name)


if __name__ == "__main__":
    main()
