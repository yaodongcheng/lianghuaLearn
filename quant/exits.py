# -*- coding: utf-8 -*-
"""
quant/exits.py — ③ 离场层：三档用法，由易到难

1. 参数工厂 ExitSpec（覆盖 90% 场景）：
       ExitSpec(take_profit=0.05, max_hold=20)                 # +5% 止盈，20 日超期
       ExitSpec(take_profit=0.10, stop_loss=0.05, max_hold=60) # 加止损
       ExitSpec(trail_activate=0.05, trail_pct=0.03, max_hold=60)  # 移动止盈
       ExitSpec(take_profit=0.05, max_hold=20, min_hold=5)     # 基金：最少拿 5 天
2. 现成函数：exit_below_ma(20)（跌破 MA20 离场）、exit_trailing(0.10)
3. 完全自定义：按 def fn(position, row, hist) -> str | None 写，≤5 行

教学要点：
- 离场优先级（同一天多个条件同时触发时）：止损 → 止盈 → 移动止盈 → 超期。
  这个顺序与知乎 v3 引擎逐字一致（回归测试依赖它），改动会改变"卖出原因"标签。
- min_hold 是基金 7 天惩罚性赎回费的防线：未满 min_hold 天，止盈/止损/移动止盈
  全部禁卖；但【超期】不受 min_hold 限制（max_hold 是绝对的，见 Knowledge/funds.md）。
- hist 是引擎给的"截至当日"切片：想拿未来数据？物理上没有。这就是契约级防未来函数。
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)  # frozen：参数定稿后不可改，防止实验中途改参数口径混乱
class ExitSpec:
    """离场参数包。全 None = 永不主动离场（买入持有）。"""
    take_profit: float = None      # 固定止盈，如 0.05 = +5%
    stop_loss: float = None        # 固定止损，如 0.07 = -7%
    max_hold: int = None           # 超期离场（交易日）
    trail_activate: float = None   # 移动止盈激活线：浮盈峰值曾达此值
    trail_pct: float = None        # 移动止盈回撤线：从持仓最高收盘回撤此值离场
    min_hold: int = 0              # 最少持有交易日（基金防 7 日惩罚费：≥5）

    def to_fn(self):
        """生成引擎认的离场函数。"""
        if (self.trail_activate is None) != (self.trail_pct is None):
            raise ValueError("trail_activate 和 trail_pct 必须成对给出（移动止盈是两个参数）")

        def exit_fn(position, row, hist):
            h, close = position.hold_days, row["close"]
            if h >= self.min_hold:   # 未满 min_hold：止盈/止损/移动止盈都禁卖
                if self.stop_loss is not None and close <= position.entry_price * (1 - self.stop_loss):
                    return "止损"
                if self.take_profit is not None and close >= position.entry_price * (1 + self.take_profit):
                    return "止盈"
                if (self.trail_activate is not None
                        and position.peak_close >= position.entry_price * (1 + self.trail_activate)
                        and close <= position.peak_close * (1 - self.trail_pct)):
                    return "移动止盈"
            if self.max_hold is not None and h >= self.max_hold:   # 超期是绝对的
                return "超期"
            return None
        exit_fn.__name__ = f"ExitSpec({self.describe()})"   # 报告回显用
        return exit_fn

    def describe(self):
        """报告回显用的一句话描述（每张报告自带"实验条件"，防混淆）。"""
        parts = []
        if self.take_profit is not None:
            parts.append(f"止盈+{self.take_profit:.0%}")
        if self.stop_loss is not None:
            parts.append(f"止损-{self.stop_loss:.0%}")
        if self.trail_activate is not None:
            parts.append(f"移动止盈{self.trail_activate:.0%}/{self.trail_pct:.0%}")
        if self.max_hold is not None:
            parts.append(f"{self.max_hold}日超期")
        if self.min_hold:
            parts.append(f"最少持有{self.min_hold}日")
        return " / ".join(parts) if parts else "永不主动离场（买入持有）"


def adjust_for_fund(rule, kind):
    """基金模式口径调整（三个入口共用：report.run_experiment / plot / plot_compare）：
    ExitSpec 的 min_hold 提到 5 个交易日（覆盖 7 个自然日 1.5% 惩罚性赎回费，
    见 Knowledge/funds.md）；非基金标的或非 ExitSpec 原样返回。"""
    if kind == "fund" and isinstance(rule, ExitSpec) and rule.min_hold < 5:
        print("※ 基金模式：min_hold 自动提到 5 个交易日（覆盖 7 个自然日 1.5% 惩罚性赎回费）")
        return replace(rule, min_hold=5)
    return rule


def exit_below_ma(n=20):
    """收盘跌破 MA(n) 离场（趋势策略常用，如 MA20"生命线"）。"""
    def exit_fn(position, row, hist):
        if len(hist) < n:
            return None
        if row["close"] < hist["close"].rolling(n).mean().iloc[-1]:
            return f"跌破MA{n}"
        return None
    exit_fn.__name__ = f"跌破MA{n}离场"
    return exit_fn


def exit_trailing(pct=0.10):
    """从持仓最高收盘价回撤 pct 离场（无激活线版移动止盈，趋势策略用）。"""
    def exit_fn(position, row, hist):
        if row["close"] <= position.peak_close * (1 - pct):
            return f"高点回撤{pct:.0%}"
        return None
    exit_fn.__name__ = f"高点回撤{pct:.0%}离场"
    return exit_fn
