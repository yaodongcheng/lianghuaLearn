# -*- coding: utf-8 -*-
"""策略：年线牛熊过滤（trend_ma250）——趋势型标的的教科书打法（plans/15）

适用场景（plans/14 结论的镜像）：bottom_reversal 这类抄底策略适合"区间震荡"的
均值回复标的；半导体/新能源这类【趋势型】行业（大涨大跌走单边），抄底策略
会在阴跌里反复接飞刀、在牛市 +7% 就下车。趋势型标的的标准解法是【顺势】：
站在年线（MA250）之上才持有，跌破年线离场——不预测底在哪，等趋势自己
走出来才跟。

规则（1 个参数，250=年线是教科书值，不调）：
- 入场：收盘价【首日】站上 MA250（前一天还在线下 = 趋势由空转多的确认）
- 离场：收盘价跌破 MA250（趋势由多转空）

教学要点：
1. 它是"右侧"策略的极致：买得比底部高、卖得比顶部低（两头让利），
   换来的是不在 2021-2024 那种三年阴跌里硬扛（半导体持有回撤曾超 -60%）。
2. 与 ma_cross(MA5/20) 的区别只在均线长度，但性质完全不同：
   MA250 一年交易 1~2 次，适合场外基金（赎回费按持有期阶梯收，
   快进快出被费率打死）；MA5/20 一年十几次，是场内品种的频率。
3. 震荡市会被 whipsaw（年线附近反复小幅打脸）——它和抄底策略是互补的，
   用错标的类型两者都会失效（plans/14：上证上年线策略大概率跑输抄底）。
"""
from quant import Strategy
from quant.exits import exit_below_ma
from quant.indicators import cal_ma
from quant.signals import cross_down

MA_N = 250   # 年线 ≈ 一年的交易日数（A股约 244，250 是常用整数值）


def entry(df):
    """收盘首日在年线之上（昨日还在线下 → 由空转多的首日，避免天天发信号）。"""
    return cross_down(df["close"] > cal_ma(df["close"], MA_N))


STRATEGY = Strategy(
    name="trend_ma250",
    entry_fn=entry,
    exit=exit_below_ma(MA_N),          # 收盘跌破年线离场（现成离场函数）
    note="年线之上才持有、跌破离场；年交易约 1~2 次，为场外行业基金设计；"
         "趋势型标的专用，震荡市会被 whipsaw（plans/15 实测）",
)
