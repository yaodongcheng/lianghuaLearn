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


__all__ = ["Strategy", "ExitSpec", "run_backtest", "assert_no_lookahead"]
