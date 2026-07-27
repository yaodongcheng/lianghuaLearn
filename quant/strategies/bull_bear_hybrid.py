# -*- coding: utf-8 -*-
"""策略：牛熊双模式混合（bull_bear_hybrid）

解决的问题：纯超跌策略（如 bias_oversold）只在熊市恐慌时有信号，
牛市全程空仓踏空——资金利用率低。本策略用 MA250（年线）做牛熊开关：
- 年线之上（牛市模式）：金叉趋势跟随 + 移动止盈，吃整段趋势；
- 年线之下（熊市模式）：BIAS 超跌抄底 + 固定止盈，吃恐慌修复（原配方）。

教学要点：
1. 为什么移动止盈能"吃牛市"：固定止盈 +5% 在牛市里卖飞主升浪；
   移动止盈不设上限，只要趋势不破就一直拿着，回撤 7% 才走——
   用"让利润奔跑"换"少赚最后一段"。
2. 模式锁定在【买入当天】：持仓中途指数上下穿越年线不改变打法。
   否则会出现"按牛市规则买的仓位，熊市反弹 +5% 就被卖掉"的规则打架。
   实现上用 hist.loc[:entry_date] 回查买入日状态——hist 是引擎给的
   截至当日切片，物理上无未来数据（见 engine.py 契约）。
3. 熊市模式不抄金叉：年线之下均线空头排列，金叉多是下跌中继的假信号。

⚠️ 实测教训（2026-07-27，2018-07~2026-07 三指数对照，此策略作为"验证过的
反面教材"保留——混合两种 alpha 来源，过渡损耗可能吃掉牛市收益）：
- 创业板指(趋势市): 混合 +75.8% vs 纯超跌 -8.0% vs 买入持有 +119.1%
- 上证指数(震荡市): 混合 -3.2%  vs 纯超跌 +43.9%
- 沪深300(半趋势):  混合 +28.7% vs 纯超跌 +48.2%
结论：牛市端趋势择时两头不讨好——趋势市跑不赢"拿着不动"，震荡市被
whipsaw 反复止损。真正解决"资金没吃到牛市"的正解是【核心-卫星配置】：
核心仓长期持有指数基金吃贝塔（不择时），卫星仓专做超跌修复（空仓期
放货币基金/逆回购）——两笔钱分开管，而不是一套规则来回切换。
"""
from quant import Strategy
from quant.indicators import cal_ma
from quant.signals import cross_down, sig_bias_oversold

# —— 参数（集中放顶部，方便调参实验）——
REGIME_MA = 250        # 牛熊分界线：年线
BULL_TP_ACTIVATE = 0.06   # 牛市仓移动止盈激活线：浮盈峰值曾达 +6%
BULL_TP_PCT = 0.05        # 牛市仓移动止盈回撤线：从最高收盘回撤 5% 离场
BULL_MAX_HOLD = 120       # 牛市仓超期兜底（交易日，约半年）
BEAR_TAKE_PROFIT = 0.05   # 熊市仓固定止盈（沿用 v3 配方）
BEAR_MAX_HOLD = 20        # 熊市仓超期（沿用 v3 配方）


def _in_bull(hist_close):
    """给定截至某日的收盘序列，判断该日是否处于牛市模式（收盘 > 年线）。"""
    if len(hist_close) < REGIME_MA:
        return False       # 年线还没"暖机"出来，保守按熊市处理
    return hist_close.iloc[-1] > cal_ma(hist_close, REGIME_MA).iloc[-1]


def entry(df):
    """牛熊开关 + 两套入场：牛市金叉，熊市超跌（全部为因果信号，过前缀门禁）。
    牛市模式额外要求【年线向上】（ma > 5 个交易日前）：年线向下时的金叉
    多是熊市反抽的假信号（2021-2023 震荡区的 whipsaw 全是这种）。"""
    ma = cal_ma(df["close"], REGIME_MA)
    bull = (df["close"] > ma) & (ma > ma.shift(5))                 # 年线之上且向上
    golden = cross_down(cal_ma(df["close"], 5) > cal_ma(df["close"], 20))
    bull_entry = bull & golden                                      # 牛市：金叉首日
    bear_entry = (df["close"] <= ma) & sig_bias_oversold(df)        # 熊市：BIAS20≤-6% 首日
    return bull_entry | bear_entry


def hybrid_exit(position, row, hist):
    """按【买入当天】的牛熊模式执行对应离场（模式全程锁定，见模块 docstring）。"""
    bull_at_entry = _in_bull(hist.loc[:position.entry_date, "close"])
    h, close = position.hold_days, row["close"]

    if bull_at_entry:
        # 牛市仓三件套（优先级：年线破位 → 移动止盈 → 超期）：
        # 1) 年线破位 = 逻辑止损：买入理由是"站在年线上"，理由消失立即走，
        #    避免 v1 那种"跌破熊市还按牛市规则裸扛 120 天"的大亏（-15.5% 的教训）
        if not _in_bull(hist["close"]):
            return "牛·年线破位"
        # 2) 移动止盈（无固定止盈上限，让趋势奔跑）
        if (position.peak_close >= position.entry_price * (1 + BULL_TP_ACTIVATE)
                and close <= position.peak_close * (1 - BULL_TP_PCT)):
            return "牛·移动止盈"
        # 3) 超期兜底
        if h >= BULL_MAX_HOLD:
            return "牛·超期"
    else:
        # 熊市仓：快进快出（与 bias_oversold 原配方一致）
        if close >= position.entry_price * (1 + BEAR_TAKE_PROFIT):
            return "熊·止盈"
        if h >= BEAR_MAX_HOLD:
            return "熊·超期"
    return None


hybrid_exit.__name__ = (
    f"牛熊双模式离场（牛:移动止盈{BULL_TP_ACTIVATE:.0%}/{BULL_TP_PCT:.0%}或{BULL_MAX_HOLD}日"
    f" / 熊:止盈{BEAR_TAKE_PROFIT:.0%}或{BEAR_MAX_HOLD}日）"
)

STRATEGY = Strategy(
    name="bull_bear_hybrid",
    entry_fn=entry,
    exit=hybrid_exit,
    note=("年线之上(且向上)金叉+移动止盈吃趋势，年线之下BIAS超跌+5%止盈吃修复；"
          "模式锁定买入日。实测(2018-07~2026-07)：趋势品种有效(创业板指+75.8%)，"
          "震荡品种失效(上证-3.2%、中证500持平，whipsaw损耗)；"
          "且各品种均跑不赢更简单的替代方案——详见文件头教训")
)
