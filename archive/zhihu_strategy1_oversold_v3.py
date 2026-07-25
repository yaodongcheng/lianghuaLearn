# -*- coding: utf-8 -*-
"""
zhihu_strategy1_oversold_v3.py — 超跌判断指标对比 & 止盈方式对比（计划 06 第三轮）

回答用户提出的两个学习问题：
  Q1: 什么指标能"证明"当前超跌了？—— 用同一套买卖框架，只换入场信号，公平对比：
      ① 10日收益率 ≤ -7%（动量急跌，v2 基线）
      ② RSI(6) ≤ 20（经典超卖，公式按 Knowledge/technical_indicators.md 的 Wilder 口径）
      ③ 乖离率 BIAS(20) ≤ -6%（价格偏离 20 日均线过远）
      ④ KDJ 的 D < 20（复用 wheels.md 的 cal_kdj 轮子）
      ⑤ 收盘跌破 BOLL 下轨（MA20 - 2σ）
      ⑥ 距 60 日高点回撤 ≥8%（v1 基线）
  Q2: 固定止盈 vs 移动止盈（跟随止盈）—— 同样的入场，只换离场方式：
      A: 固定止盈 +5%（v2 基线）
      B: 移动止盈：浮盈曾达 +3% 后，从持仓最高收盘回撤 3% 离场
      C: 移动止盈 + 放宽持仓到 60 日（给利润奔跑的空间）
      （依据 Knowledge/exit_rules.md：移动止盈的"锚"在抬高的峰值上，参数用平庸整数）

统一规则：T 日收盘出信号 → T+1 开盘成交；成本双边 0.1%；超期离场。
用法：python zhihu_strategy1_oversold_v3.py
"""

import sys

import pandas as pd

from fetch_data import fetch_daily

sys.stdout.reconfigure(encoding="utf-8")

START = "2018-07-01"   # 与前两轮同一回测区间，结果可比
COST = 0.001


def cross_down(cond):
    """条件从 False 变 True 的"首日"（避免连续满足时天天发信号）。"""
    return cond & ~cond.shift(1, fill_value=False)


# ------------------------------------------------------------
# 超跌指标实现（公式对照 Knowledge/technical_indicators.md）
# ------------------------------------------------------------
def cal_rsi(close, n=6):
    """RSI（Wilder 平滑口径）：ewm(alpha=1/n) 即 Wilder 平滑。国内软件同口径。"""
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down
    return 100 - 100 / (1 + rs)


def cal_bias(close, n=20):
    """乖离率 BIAS：(收盘 - MA_n) / MA_n。负得越多 = 偏离均线越远 = 越超跌。"""
    return close / close.rolling(n).mean() - 1


def make_signals(df):
    """在完整数据（含回测起点之前的预热段）上算信号，再切到回测区间。"""
    close, ma20 = df["close"], df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()          # BOLL 用样本标准差（ddof=1，口径差异无害）
    kdj_d = _kdj_d(df)
    signals = {
        "10日跌≥7%": cross_down(close.pct_change(10) <= -0.07),
        "RSI6≤20": cross_down(cal_rsi(close, 6) <= 20),
        "BIAS20≤-6%": cross_down(cal_bias(close, 20) <= -0.06),
        "KDJ-D<20": cross_down(kdj_d < 20),
        "破BOLL下轨": cross_down(close < ma20 - 2 * std20),
        "60日高点回撤≥8%": cross_down(close / close.rolling(60).max() - 1 <= -0.08),
    }
    return {k: v.loc[START:] for k, v in signals.items()}


def _kdj_d(df, n=9):
    """cal_kdj 轮子的内联版（与 wheels.md 代码逐字一致，仅取 D 列返回）。"""
    low_min = df["low"].rolling(n, min_periods=n).min()
    low_min.fillna(value=df["low"].expanding().min(), inplace=True)
    high_max = df["high"].rolling(n, min_periods=n).max()
    high_max.fillna(value=df["high"].expanding().max(), inplace=True)
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=2).mean()        # com=2 → α=1/3，等价于国内口径 SMA(RSV,3,1)
    return k.ewm(com=2).mean()       # D


# ------------------------------------------------------------
# 通用回测：支持固定止盈 / 移动止盈 / 止损 / 超期
# ------------------------------------------------------------
def run_backtest(df, entry_signal, cost=COST, cooldown_days=10,
                 take_profit=None, stop_loss=None, max_hold=20,
                 trail_activate=None, trail_pct=None):
    """无未来函数回测：T 日收盘信号 → T+1 开盘成交。

    离场优先级（收盘判断）：止损 → 固定止盈 → 移动止盈 → 超期
    移动止盈：浮盈峰值曾达 trail_activate 后，收盘从持仓最高收盘回撤 trail_pct 离场
    """
    sig = entry_signal.fillna(False)
    trades, equity = [], []
    cash, shares, entry_price, entry_date, hold = 1.0, 0.0, None, None, 0
    entry_cash, peak_close = None, None
    pending_buy, pending_sell = False, None
    cooldown = 0

    for i, (date, row) in enumerate(df.iterrows()):
        if pending_buy and shares == 0:
            entry_cash = cash
            shares = cash * (1 - cost) / row["open"]
            cash, entry_price, entry_date, hold = 0.0, row["open"], date, 0
            peak_close = row["close"]
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

        if shares > 0:
            hold += 1
            peak_close = max(peak_close, row["close"])
            if stop_loss is not None and row["close"] <= entry_price * (1 - stop_loss):
                pending_sell = "止损"
            elif take_profit is not None and row["close"] >= entry_price * (1 + take_profit):
                pending_sell = "止盈"
            elif (trail_activate is not None
                  and peak_close >= entry_price * (1 + trail_activate)
                  and row["close"] <= peak_close * (1 - trail_pct)):
                pending_sell = "移动止盈"
            elif hold >= max_hold:
                pending_sell = "超期"
        elif cooldown > 0:
            cooldown -= 1
        elif sig.iloc[i]:
            pending_buy = True

        equity.append(cash + shares * row["close"])

    return pd.DataFrame(trades), pd.Series(equity, index=df.index)


def metrics(trades, eq, df):
    """返回 (年化, 最大回撤, 交易数, 胜率, 平均每笔)。"""
    n_years = (df.index[-1] - df.index[0]).days / 365.25
    total = eq.iloc[-1] / eq.iloc[0] - 1
    ann = (1 + total) ** (1 / n_years) - 1 if total > -1 else -1
    mdd = (eq / eq.cummax() - 1).min()
    if len(trades):
        return ann, mdd, len(trades), (trades["收益率"] > 0).mean(), trades["收益率"].mean()
    return ann, mdd, 0, float("nan"), float("nan")


# ------------------------------------------------------------
# Part 1：超跌指标公平对比（同一离场：+5% 固定止盈 / 20 日超期）
# ------------------------------------------------------------
def part1(df, name, signals):
    print(f"\n{'=' * 74}\nPart 1：{name}——六种'超跌'定义公平对比（离场统一：+5%止盈/20日超期）\n{'=' * 74}")
    print(f"{'超跌定义':<14}{'信号数':>5}{'交易数':>5}{'胜率':>7}{'平均每笔':>9}{'年化':>8}{'最大回撤':>9}")
    for label, sig in signals.items():
        trades, eq = run_backtest(df, sig, take_profit=0.05, max_hold=20)
        ann, mdd, n, win, avg = metrics(trades, eq, df)
        print(f"{label:<14}{int(sig.sum()):>5}{n:>5}{win:>7.0%}{avg:>9.1%}{ann:>8.1%}{mdd:>9.1%}")


# ------------------------------------------------------------
# Part 2：固定止盈 vs 移动止盈（同一入场信号）
# ------------------------------------------------------------
def part2(df, name, signals):
    entries = {"10日跌≥7%": signals["10日跌≥7%"], "RSI6≤20": signals["RSI6≤20"]}
    exits = [
        ("A 固定止盈+5% / 20日", dict(take_profit=0.05, max_hold=20)),
        ("B 移动止盈3%/3% / 20日", dict(trail_activate=0.03, trail_pct=0.03, max_hold=20)),
        ("C 移动止盈3%/3% / 60日", dict(trail_activate=0.03, trail_pct=0.03, max_hold=60)),
        ("D 移动止盈5%/5% / 60日", dict(trail_activate=0.05, trail_pct=0.05, max_hold=60)),
    ]
    print(f"\n{'=' * 74}\nPart 2：{name}——固定止盈 vs 移动止盈（同一入场，只换离场）\n{'=' * 74}")
    print(f"{'入场信号':<12}{'离场方式':<26}{'交易数':>5}{'胜率':>7}{'平均每笔':>9}{'年化':>8}{'最大回撤':>9}")
    for sig_label, sig in entries.items():
        for exit_label, kw in exits:
            trades, eq = run_backtest(df, sig, **kw)
            ann, mdd, n, win, avg = metrics(trades, eq, df)
            print(f"{sig_label:<12}{exit_label:<26}{n:>5}{win:>7.0%}{avg:>9.1%}{ann:>8.1%}{mdd:>9.1%}")


def main():
    for symbol, name in [("000001", "上证指数"), ("000300", "沪深300")]:
        df = fetch_daily("idx", symbol, start="20180101")
        df = df.set_index(pd.to_datetime(df["date"])).sort_index()
        signals = make_signals(df)
        bt = df.loc[START:]
        part1(bt, name, signals)
        part2(bt, name, signals)


if __name__ == "__main__":
    main()
