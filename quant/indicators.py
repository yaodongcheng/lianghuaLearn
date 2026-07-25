# -*- coding: utf-8 -*-
"""
quant/indicators.py — ② 指标层：技术指标纯函数

教学要点：
- 每个函数都是【纯函数】：输入 Series/df，输出指标值，不改输入、不读全局状态。
  纯函数才能过 assert_no_lookahead 的因果性测试（截断重算结果不变）。
- 公式全部对照 Knowledge/technical_indicators.md（国内行情软件口径），
  实现与标准定义有出入时会在注释里标明。
- 指标是策略间共享的代码：复用靠 import 本模块，不靠父类继承（组合优于继承）。
"""

import pandas as pd


def cal_ma(close, n):
    """简单均线 SMA：最近 N 日收盘的算术平均。前 N-1 天为 NaN（数据不够）。"""
    return close.rolling(n).mean()


def cal_rsi(close, n=6):
    """RSI（Wilder 平滑口径）：ewm(alpha=1/n) 即 Wilder 平滑，国内软件同口径。
    注意别用 rolling(n).mean()（简单平均）——那是另一种口径，数值对不上行情软件。"""
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down
    return 100 - 100 / (1 + rs)


def cal_bias(close, n=20):
    """乖离率 BIAS：(收盘 - MA_n) / MA_n。负得越多 = 偏离均线越远 = 越超跌。
    对"跌得快"敏感（均线是平均成本，价格急杀会瞬间偏离它），天然捕捉短期超跌。"""
    return close / close.rolling(n).mean() - 1


def cal_macd(close, fast=12, slow=26, signal=9):
    """MACD 三件套，返回 DataFrame(dif, dea, bar)。
    bar = 2×(dif-dea) 是国内软件口径（国外为 1×）；判断金叉死叉不受影响。"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"dif": dif, "dea": dea, "bar": (dif - dea) * 2})


def cal_kdj(df, n=9):
    """KDJ（9,3,3），返回 DataFrame(kdj_k, kdj_d, kdj_j)。需要 df 含 high/low/close。
    国内 SMA(X,3,1) = α=1/3 的指数平滑 = ewm(com=2)（α=1/(1+com)）。
    前 n-1 日用 expanding 填充让早期有值；行情软件从第 9 天才显示，早期差异正常。"""
    low_min = df["low"].rolling(n, min_periods=n).min()
    low_min = low_min.fillna(df["low"].expanding().min())
    high_max = df["high"].rolling(n, min_periods=n).max()
    high_max = high_max.fillna(df["high"].expanding().max())
    rsv = (df["close"] - low_min) / (high_max - low_min) * 100
    k = rsv.ewm(com=2).mean()
    d = k.ewm(com=2).mean()
    return pd.DataFrame({"kdj_k": k, "kdj_d": d, "kdj_j": 3 * k - 2 * d})


def cal_boll(close, n=20, k=2):
    """布林带，返回 (中轨, 上轨, 下轨)：中轨=MA20，上下轨=中轨±kσ。
    σ 用样本标准差（pandas 默认 ddof=1；不同软件口径差一点属正常）。"""
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    return mid, mid + k * std, mid - k * std
