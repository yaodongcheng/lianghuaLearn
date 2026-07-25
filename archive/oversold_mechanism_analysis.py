# -*- coding: utf-8 -*-
"""
oversold_mechanism_analysis.py — "超跌为什么反弹 / 何时会失效"的数据分析（计划 06 第四轮）

用户之问：超跌为什么会反弹？是不是因为"有指标支撑"？
如果一路下跌，越跌越抄不就套牢了吗？——这正是均值回归策略的生死问题。

分析框架（注意：Part 1/2 是【统计研究】不是回测——用未来数据算"条件收益"是合法的
研究手段，用来回答"信号有没有信息含量"；但它不能当交易信号，赚钱与否仍要靠
无未来函数的回测（Part 3）验证）：

  Part 1【信息含量】超跌信号日 vs 普通交易日的"未来 20 日收益"分布对比。
        信号日后收益显著更好 → 信号确实含"反弹概率高"的信息；
        差不多 → 所谓超跌只是自我安慰。
  Part 2【牛熊分组】按信号日收盘是否在 250 日线（年线）上方分组。
        假设：年线上方的超跌多为"错杀"（恐慌事件冲击），反弹概率高；
              年线下方的超跌多为"趋势中继"（基本面下行），容易越跌越抄。
  Part 3【过滤器回测】把"只在年线上方抄底"加进无未来函数回测，验证过滤器价值。
  Part 4【失败案例归因】列出亏损交易，看它们都死在什么环境里。

用法：python oversold_mechanism_analysis.py
"""

import sys

import pandas as pd

from fetch_data import fetch_daily
from zhihu_strategy1_oversold_v3 import run_backtest, cross_down, cal_rsi, cal_bias

sys.stdout.reconfigure(encoding="utf-8")

START = "2018-07-01"   # 与前两轮回测同一区间
HORIZON = 20           # 观察"未来 N 日收益"的窗口


def fwd_stats(fwd_ret, mask, label):
    """打印 mask 为 True 的日子的未来收益分布。"""
    r = fwd_ret[mask].dropna()
    if len(r) == 0:
        print(f"{label:<28} 样本 0")
        return
    print(f"{label:<28} 样本{len(r):>4}   均值{r.mean():>7.1%}   中位{r.median():>7.1%}"
          f"   P(涨≥5%){(r >= 0.05).mean():>6.0%}   P(跌≥5%){(r <= -0.05).mean():>6.0%}")


def analyze(df, name):
    close = df["close"]
    # 未来收益（仅研究用！）：今天买入、20 个交易日后卖出的收益
    fwd20 = close.shift(-HORIZON) / close - 1

    signals = {
        "BIAS20≤-6%": cross_down(cal_bias(close, 20) <= -0.06),
        "10日跌≥7%": cross_down(close.pct_change(10) <= -0.07),
        "RSI6≤20": cross_down(cal_rsi(close, 6) <= 20),
    }

    print(f"\n{'=' * 78}\n{name}\n{'=' * 78}")

    # ---------- Part 1：信号日 vs 普通日的未来 20 日收益 ----------
    print(f"\n--- Part 1 信息含量：信号日之后 {HORIZON} 日的收益，真的比普通日子好吗？---")
    all_days = pd.Series(True, index=df.index)
    fwd_stats(fwd20, all_days, "全部交易日（基准）")
    for label, sig in signals.items():
        fwd_stats(fwd20, sig, f"信号日：{label}")

    # ---------- Part 2：牛熊分组 ----------
    ma250 = close.rolling(250).mean()
    above = close > ma250
    print(f"\n--- Part 2 牛熊分组：年线上方（牛市/错杀）vs 年线下方（熊市/趋势中继）---")
    for label, sig in signals.items():
        fwd_stats(fwd20, sig & above, f"{label} + 年线上方")
        fwd_stats(fwd20, sig & ~above, f"{label} + 年线下方")

    # ---------- Part 3：过滤器回测（无未来函数）----------
    print(f"\n--- Part 3 回测：年线过滤器能否改善策略？（BIAS20≤-6% 入场，+5%止盈/20日）---")
    bt = df.loc[START:]
    sig_all = signals["BIAS20≤-6%"].loc[START:]
    sig_bull = sig_all & above.loc[START:]   # 当天收盘在年线上方（收盘已知，无未来函数）
    for label, sig in [("不过滤（全部信号）", sig_all), ("只年线上方", sig_bull)]:
        trades, eq = run_backtest(bt, sig, take_profit=0.05, max_hold=20)
        n_years = (bt.index[-1] - bt.index[0]).days / 365.25
        total = eq.iloc[-1] - 1
        ann = (1 + total) ** (1 / n_years) - 1 if total > -1 else -1
        mdd = (eq / eq.cummax() - 1).min()
        win = (trades["收益率"] > 0).mean() if len(trades) else float("nan")
        print(f"{label:<16} 交易{len(trades):>3}  胜率{win:>5.0%}  "
              f"平均每笔{trades['收益率'].mean() if len(trades) else 0:>6.1%}"
              f"  年化{ann:>6.1%}  最大回撤{mdd:>7.1%}")

    # ---------- Part 4：亏损交易归因 ----------
    print(f"\n--- Part 4 亏损交易都死在什么环境？（BIAS 信号、不过滤版本）---")
    trades, _ = run_backtest(bt, sig_all, take_profit=0.05, max_hold=20)
    losers = trades[trades["收益率"] < 0].copy()
    if len(losers) == 0:
        print("没有亏损交易")
    else:
        for _, t in losers.iterrows():
            d = pd.Timestamp(t["买入日"])
            env = "年线上方" if above.get(d, False) else "年线下方"
            print(f"  {t['买入日']} 买 → {t['卖出日']} 卖  {t['收益率']:>6.1%}  {env}")


def main():
    for symbol, name in [("000001", "上证指数"), ("000300", "沪深300")]:
        df = fetch_daily("idx", symbol, start="20180101")
        df = df.set_index(pd.to_datetime(df["date"])).sort_index()
        analyze(df, name)


if __name__ == "__main__":
    main()
