# -*- coding: utf-8 -*-
"""
exit_rules_demo.py — 用真实数据演示几种"离场规则"在两个真实行情片段中的表现
片段一：永赢半导体C（025209）2026-04 ~ 2026-07（4-6月大涨、7月暴跌）
片段二：腾讯（00700）2021 年 2 月历史大顶前后（买在风口的人后来 -75%）

纪律（对照 backtest_checklist §1）：规则在 T 日触发 → T+1 日才成交，
不许用"当天盘中看到跌了当天收盘价跑掉"这种未来函数。
"""

import pandas as pd
from fetch_data import fetch_daily, fetch_fund_nav


def simulate(df, price_col, rules=("hold", "trail10", "trail15", "ma20")):
    """在 df 给定的窗口上逐日模拟各规则，返回 {规则: (离场日, 区间收益率)}"""
    close = df[price_col].reset_index(drop=True)
    dates = df["date"].reset_index(drop=True)
    ma20 = close.rolling(20).mean()
    results = {}
    for rule in rules:
        peak = close.iloc[0]
        exit_i = None
        for i in range(len(close)):
            peak = max(peak, close.iloc[i])  # 峰值随行情创新高不断抬高
            fire = False
            if rule == "trail10":
                fire = close.iloc[i] <= peak * 0.90   # 从最高点回撤 10%
            elif rule == "trail15":
                fire = close.iloc[i] <= peak * 0.85   # 从最高点回撤 15%
            elif rule == "ma20":
                fire = i >= 20 and close.iloc[i] < ma20.iloc[i]  # 收盘跌破 20 日均线
            if fire:
                exit_i = min(i + 1, len(close) - 1)   # 触发次日才成交
                break
        j = exit_i if exit_i is not None else len(close) - 1
        results[rule] = (dates.iloc[j], close.iloc[j] / close.iloc[0] - 1, exit_i is not None)
    return results


def show(title, df, price_col):
    print(f"\n===== {title} =====")
    r = simulate(df, price_col)
    for rule, (day, ret, exited) in r.items():
        label = {"hold": "一直持有", "trail10": "回撤10%移动止盈", "trail15": "回撤15%移动止盈",
                 "ma20": "跌破20日均线离场"}[rule]
        where = f"{day:%Y-%m-%d} 离场" if exited else f"持有到 {day:%Y-%m-%d}"
        print(f"  {label:<14} → {where}，区间收益 {ret:+.1%}")
    return r


# ===== 片段一：半导体基金的 2026 年 4~7 月 =====
fund = fetch_fund_nav("025209")
w1 = fund[fund["date"] >= "2026-04-01"].reset_index(drop=True)
show("永赢半导体C：2026-04-01 买入（小红书说的那波）", w1, "nav")

# 6 月高点冲进去的人（小红书晒收益最凶的时候），一直拿着的下场：
peak_i = w1["nav"].idxmax()
peak_day = w1["date"].iloc[peak_i]
late = (w1["nav"].iloc[-1] / w1["nav"].iloc[peak_i] - 1)
print(f"  [对照] {peak_day:%Y-%m-%d} 最高点买入并持有至今：{late:+.1%}")

# ===== 片段二：腾讯 2021 年历史大顶 =====
hk = fetch_daily("hk", "00700", start="20210101", end="20221231")
show("腾讯：2021-01-04 买入（随后 2 月见到历史大顶）", hk, "close")
