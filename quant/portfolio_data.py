# -*- coding: utf-8 -*-
"""
quant/portfolio_data.py — 组合回测的"桌面"：取数 / 日期对齐 / 今日快照

拆出来的理由：portfolio.py 只放**事件循环**（钱怎么动的纪律），
本文件放循环前后的准备与呈现——摆在策略面前的那张桌子：

    load_portfolio_navs   {显示名: 查询串} → {显示名: 价格表}（走 data 层契约）
    align_prices          多标的价格表 → 一张对齐好的收盘价矩阵
    PortfolioContext      决策函数每天看到的快照（策略能拿到的信息全在这里）

防未来函数在这一层的体现：对齐只用 ffill（向前填充=用最近**已知**净值估值，
只朝过去填、不朝未来借数据），快照的 hist 只切到决策日当天。
"""

from dataclasses import dataclass, field

import pandas as pd


def load_portfolio_navs(holdings, data_start="20130101", adjust=None):
    """{显示名: 标的查询串} → {显示名: df(仅 close 列)}，喂给组合回测。

    取数一律走 data.load_data 契约（缓存→自动下载+体检），组合层不碰 akshare。
    holdings 的查询串写法同 load_data："fund:270042" / "沪深300" / "512480"。
    adjust 透传给 load_data：个股组合传 "hfq"（后复权，见 Portfolio.adjust 的说明），
    基金/指数留 None 用各市场默认。
    """
    from quant.data import load_data     # 延迟 import：只有真要取数时才拉数据层
    nav = {}
    for name, query in holdings.items():
        df, _info = load_data(query, start=data_start, adjust=adjust)
        nav[name] = df[["close"]]
    return nav


def align_prices(nav_map):
    """多标的价格表对齐：{名称: df(date 索引)} → 一张收盘价矩阵。

    - 列 = 各标的收盘价（取每表的 close 列）
    - 日期 = 所有标的交易日的并集，缺口 ffill（如 QDII 基金遇美股假日不更新净值，
      当天按上一净值估值——这正是真实账户的估值方式）
    - 返回 (价格矩阵, 首个全员有数据的日期)：矩阵在该日期之前的行含 NaN（某标的
      还没上市），调用方应从这个日期起开始回测
    """
    closes = {}
    for name, df in nav_map.items():
        col = df["close"] if "close" in df.columns else df.iloc[:, 0]
        closes[name] = col
    px = pd.DataFrame(closes).sort_index()
    px = px[~px.index.duplicated(keep="last")]
    first_full = px.dropna().index[0]  # 最后一只上市之日 = 组合可成立之日
    return px.ffill(), first_full


@dataclass
class PortfolioContext:
    """决策函数看到的"今日快照"——策略能拿到的信息全在这里，多的一点都没有。

    字段：
        date:    今天（决策日）
        names:   成分标的名单（顺序固定）
        prices:  今日收盘价/净值 Series
        hist:    从回测起点到**今天**的价格矩阵（切片到今天，看不到未来）
        shares:  当前各标的份额 dict
        cash:    当前现金（元）
        values:  当前各标的市值 Series
        total:   当前总资产（含现金）
        weights: 当前各标的权重 Series（= values / total）

    方法 orders_for_weights 是最常用的工具：把"我想要的权重"翻译成"该买卖多少钱"。
    """
    date: pd.Timestamp
    names: list
    prices: pd.Series
    hist: pd.DataFrame
    shares: dict
    cash: float
    values: pd.Series
    total: float
    weights: pd.Series
    i: int = field(default=0, repr=False)

    @property
    def invested(self):
        """是否已经建仓（还全是现金时为 False，决策函数据此下建仓单）。"""
        return any(v > 1e-9 for v in self.shares.values())

    def orders_for_weights(self, target_weights):
        """目标权重 → 订单 {标的: 带符号金额}（正=买、负=卖）。

        差额 = 目标市值 − 当前市值。注意分母用 self.total（含现金），
        所以现金也会被这套订单花出去——建仓和调仓用的是同一段逻辑。
        """
        return {n: self.total * target_weights[n] - self.values[n] for n in self.names}
