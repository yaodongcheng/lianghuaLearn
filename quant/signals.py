# -*- coding: utf-8 -*-
"""
quant/signals.py — ③ 入场信号库：sig_*(df, **参数) -> 布尔 Series

契约（每个新信号必须满足）：
1. 输入标准 df（date 索引 + open/high/low/close/volume），输出与 df 等长布尔 Series，
   True = 当天收盘出现买入信号（引擎次日开盘才成交）
2. 只能用当天及以前的数据——每个新信号必须过 engine.assert_no_lookahead 门禁
   （前缀不变性测试：截断重算，前 k 项逐日一致）
3. 多策略复用的通用信号才收进本模块；单策略专用的入场逻辑写在策略文件里

信号实测表现见 Knowledge/zhihu/吃超跌恐慌修复策略.md（2026-07-25 知乎案例）。
"""

from quant.indicators import cal_bias, cal_boll, cal_kdj, cal_rsi


def cross_down(cond):
    """条件从 False 变 True 的"首日"（避免连续满足时天天发信号）。
    名字叫 cross_down 但它是通用的"首日触发"：金叉首日也能用（cond=短均线>长均线）。
    shift(1, fill_value=False) 的写法可避免 pandas 新版 fillna 降类型警告。"""
    return cond & ~cond.shift(1, fill_value=False)


def sig_crash(df, n=10, threshold=-0.07):
    """N 日收益率 ≤ threshold（短期急跌、恐慌抛售）。胜率之王，信号最稀（年均 1-2 次）。"""
    return cross_down(df["close"].pct_change(n) <= threshold)


def sig_rsi_oversold(df, n=6, level=20):
    """RSI(n) ≤ level（经典超卖）。信号偏多、年化高（上证），但回撤大。"""
    return cross_down(cal_rsi(df["close"], n) <= level)


def sig_bias_oversold(df, n=20, threshold=-0.06):
    """BIAS(n) ≤ threshold（价格偏离均线过远）。v3 实测综合最佳，两指数都稳。"""
    return cross_down(cal_bias(df["close"], n) <= threshold)


def sig_kdj_d_oversold(df, n=9, level=20):
    """KDJ 的 D < level。实测平庸。"""
    return cross_down(cal_kdj(df, n)["kdj_d"] < level)


def sig_boll_lower(df, n=20, k=2):
    """收盘跌破 BOLL 下轨（MA - kσ）。信号太频繁（年均 6+ 次），实测失效。"""
    _, _, lower = cal_boll(df["close"], n, k)
    return cross_down(df["close"] < lower)


def sig_drawdown(df, n=60, threshold=-0.08):
    """距 N 日高点回撤 ≥ threshold。慢半拍，容易接阴跌飞刀。"""
    return cross_down(df["close"] / df["close"].rolling(n).max() - 1 <= threshold)
