# -*- coding: utf-8 -*-
"""策略：MACD 金叉买、死叉卖（教科书经典版）——plans/02 交付。

规则：DIF 上穿 DEA（金叉）首日入场；DIF 下穿 DEA（死叉）离场。
参数 (12,26,9) 是全球默认，不优化——教科书用什么就用什么，改了反而说不清。
教学定位：金叉死叉是最经典的趋势信号，"震荡市被反复打脸"也是公论，
本回测用沪深300 亲证这句话（plans/02：首个回测，对标买入持有）。
"""
from quant import Strategy
from quant.indicators import cal_macd
from quant.signals import cross_down

WARMUP = 35          # 26 日慢线 + 9 日 DEA 平滑，此前 DIF/DEA 没稳定，不判断


def entry(df):
    macd = cal_macd(df["close"])
    return cross_down(macd["dif"] > macd["dea"])          # 金叉首日（cross_down=通用首日触发）


def exit_fn(position, row, hist):
    """收盘时 DIF < DEA（死叉）离场。hist 含当日及之前的全部历史。"""
    if len(hist) < WARMUP:
        return None
    macd = cal_macd(hist["close"])
    if macd["dif"].iloc[-1] < macd["dea"].iloc[-1]:
        return "MACD死叉"
    return None


exit_fn.__name__ = "MACD死叉离场"

STRATEGY = Strategy(
    name="macd_cross",
    entry_fn=entry,
    exit=exit_fn,
    note="教科书经典：趋势段吃得到、震荡市被反复打脸（plans/02 首个回测）",
)
