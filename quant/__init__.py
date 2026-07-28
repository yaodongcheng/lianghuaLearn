# -*- coding: utf-8 -*-
"""
quant/ — 回测框架（分层：data → indicators → signals/exits → engine → metrics/report）

设计原则（详细讨论见 plans/07-backtest-framework.md）：
- 下层不 import 上层：上层怎么改，下层一行不用动
- 策略契约是【函数签名】不是基类：entry_fn(df)->bool Series /
  exit_fn(position,row,hist)->str|None，策略不 import 引擎 → 解耦最彻底
- Strategy 只是登记元数据的"名片"（dataclass），不是基类
"""

from dataclasses import dataclass

from quant.engine import assert_no_lookahead, run_backtest
from quant.exits import ExitSpec


@dataclass(frozen=True)
class Strategy:
    """策略名片：一套打法 = 入场函数 + 离场规则 + 备注。
    exit 可以给 ExitSpec（参数工厂）或自定义离场函数，引擎都能用。"""
    name: str
    entry_fn: object     # df -> 布尔 Series
    exit: object         # ExitSpec 或 exit_fn(position, row, hist)
    note: str = ""       # 实测表现/来源——strategies/ 同时是策略档案库

    def exit_fn(self):
        return self.exit.to_fn() if isinstance(self.exit, ExitSpec) else self.exit

    def exit_desc(self):
        if isinstance(self.exit, ExitSpec):
            return self.exit.describe()
        return getattr(self.exit, "__name__", "自定义离场函数")


@dataclass(frozen=True)
class Portfolio:
    """组合名片：一套【资产配置】打法 = 买哪几只 + 一个决策函数。

    与 Strategy 的分工（两类不同的问题，所以是两张名片、两个引擎）：
        Strategy  择时：单标的"何时进、何时出"    entry_fn(df)->bool / exit_fn(...)
        Portfolio 配置：多标的"钱怎么分、何时再分" decide_fn(ctx)->{标的: 带符号金额}

    契约是【函数签名】而不是配置表：所以再平衡只是**其中一种**决策函数，
    以后写网格、定投、动量轮动，都还是这同一个契约、同一个引擎。

    字段：
        holdings:   {显示名: 标的查询串}，查询串写法同 load_data
                    （"fund:270042" / "沪深300" / "512480"）
        decide_fn:  决策函数，由 quant/rebalance.py 的工厂生成（带参数）
        data_start: 取数起点（早于成分成立日也没关系，引擎会等全员就绪）
        adjust:     复权方式（None=各市场默认）。**个股组合务必写 "hfq"**：
                    前复权是"以今天为基准向前减分红"，巨额分红股的历史价会被减成
                    负数（兖矿能源 2021-01 的 qfq 价 = −1.01 元）→ 负价买入=负份额，
                    账目直接爆炸；后复权价格恒正，语义就是"分红再投资"。
        note:       实测表现/来源——portfolios/ 同时是组合档案库
    """
    name: str
    holdings: dict
    decide_fn: object
    data_start: str = "20130101"
    adjust: str = None
    note: str = ""

    def decide_desc(self):
        """一行决策规则回显（每张报告自带实验条件，防混淆）。"""
        return getattr(self.decide_fn, "desc", None) \
            or getattr(self.decide_fn, "__name__", "自定义决策函数")

    def describe(self):
        """一行完整实验条件：成分名单 + 决策规则。"""
        return f"{' + '.join(self.holdings)}｜{self.decide_desc()}"


__all__ = ["Strategy", "Portfolio", "ExitSpec", "run_backtest", "assert_no_lookahead"]
