# -*- coding: utf-8 -*-
"""
quant/report.py — ⑤ 评估层：从回测产出到人能看的报告

- print_report：单策略完整报告（回显三要素：标的/策略/离场参数——每张报告自带
  "实验条件"，防混淆）+ 样本量/参数数警报（防过拟合机制，不靠自觉）
- compare_table：多组结果对比表（信号对比、离场对比通用）
- param_sweep：参数扰动表一键出（参数轻微扰动就崩 = 过拟合脆弱策略）
- split_sample：样本内/外切分工具（留一段"从未见过的考试"）
- run_experiment：run.py 实验台的总装函数（取数→回测→报告一条龙）
"""

import inspect

import pandas as pd

from quant import metrics
from quant.data import load_data
from quant.engine import run_backtest
from quant.exits import ExitSpec


def sample_warnings(n_trades, n_params):
    """样本量/参数数警报：8 年 9 笔的"胜率 89%"和 900 笔的不是一回事。"""
    if n_trades < 30:
        print(f"⚠ 样本量警报：仅 {n_trades} 笔交易（<30），统计置信度低，"
              f"期望收益请按区间理解，别按点估计理解")
    if n_params > 4:
        print(f"⚠ 参数数警报：{n_params} 个参数（>4），过拟合风险高，"
              f"先做 param_sweep 扰动测试再下结论")


def print_report(info, strategy, exit_desc, start, cost, n_signals, trades, eq, bt):
    """单策略完整报告：三要素回显 → 汇总指标 → 逐笔明细。"""
    print(f"\n{'=' * 74}\n回测报告：{info['name']}（{info['kind']}:{info['code']}） × 策略「{strategy.name}」\n{'=' * 74}")
    print(f"区间：{bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}    "
          f"离场：{exit_desc}    成本：双边 {cost:.1%}（T 日信号 → T+1 开盘成交）")
    if strategy.note:
        print(f"策略备注：{strategy.note}")

    s = metrics.summarize(trades, eq)
    print(f"\n信号 {n_signals} 次 → 成交 {s['交易数']} 笔   胜率 {s['胜率']:.0%}   "
          f"平均每笔 {s['平均每笔']:+.1%}（盈亏比 {s['盈亏比']:.1f}）")
    print(f"总收益 {s['总收益']:+.1%}   年化 {s['年化']:+.1%}   最大回撤 {s['最大回撤']:+.1%}   "
          f"夏普 {s['夏普']:.2f}   卡玛 {s['卡玛']:.2f}")
    bh = bt["close"].iloc[-1] / bt["close"].iloc[0] - 1
    print(f"（对照·买入持有：{bh:+.1%}）")
    if info["kind"] in ("a", "hk"):
        print("※ 个股回测未处理涨跌停无法成交（主板 ±10%/创业科创 ±20%），"
              "涉及追涨停/抄底跌停的信号结论需手工复核")
    sample_warnings(s["交易数"], _count_params(strategy))

    if len(trades):
        t = trades.copy()
        t["收益率"] = (t["收益率"] * 100).round(1).astype(str) + "%"
        print(f"\n逐笔明细：\n{t.to_string(index=False)}")
    else:
        print("\n无交易（信号从未触发或被冷却期挡住）")
    return s


def compare_table(title, rows):
    """对比表：rows = [(标签, 信号数或None, trades, eq), ...]。信号数全 None 时不显示该列。"""
    show_sig = any(r[1] is not None for r in rows)
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")
    head = f"{'标签':<26}" + (f"{'信号数':>5}" if show_sig else "") + \
           f"{'交易数':>5}{'胜率':>7}{'平均每笔':>9}{'年化':>8}{'最大回撤':>9}"
    print(head)
    for label, n_sig, trades, eq in rows:
        s = metrics.summarize(trades, eq)
        win = f"{s['胜率']:.0%}" if s['交易数'] else "—"
        avg = f"{s['平均每笔']:+.1%}" if s['交易数'] else "—"
        row = f"{label:<26}" + (f"{n_sig:>5}" if show_sig else "") + \
              f"{s['交易数']:>5}{win:>7}{avg:>9}{s['年化']:>+8.1%}{s['最大回撤']:>+9.1%}"
        print(row)


def param_sweep(df, make_signal, grid, exit_fn, start, cost=0.001):
    """参数扰动表：grid = [参数dict, ...]，make_signal(df, **参数) -> 信号。
    用法：param_sweep(df, signals.sig_crash, [{"n": 5}, {"n": 10}, {"n": 20}], ...)"""
    print(f"\n参数扰动（年化收益，同一离场）：")
    for params in grid:
        sig = make_signal(df, **params)
        trades, eq = run_backtest(df, make_signal, exit_fn, start=start, cost=cost)
        label = " ".join(f"{k}={v}" for k, v in params.items())
        print(f"  {label:<28} {len(trades):>3} 笔   年化 {metrics.annual_return(eq):+.1%}   "
              f"回撤 {metrics.max_drawdown(eq):+.1%}")


def split_sample(df, cutoff):
    """样本内/外切分：用 cutoff 前定策略和参数，cutoff 后做"从未见过的考试"。"""
    return df.loc[:pd.Timestamp(cutoff)], df.loc[pd.Timestamp(cutoff):]


def _count_params(strategy):
    """参数数估算（用于过拟合警报）：入场函数带默认值的参数 + ExitSpec 非空字段。"""
    n = sum(1 for p in inspect.signature(strategy.entry_fn).parameters.values()
            if p.default is not inspect.Parameter.empty)
    if isinstance(strategy.exit, ExitSpec):
        n += sum(1 for f in ("take_profit", "stop_loss", "max_hold",
                             "trail_activate", "trail_pct", "min_hold")
                 if getattr(strategy.exit, f) not in (None, 0))
    return n


def run_experiment(target, strategy_name, start, exit_override=None,
                   data_start="20180101", cost=0.001):
    """run.py 实验台总装：选标的 + 选策略 → 完整报告。"""
    from quant.strategies import REGISTRY   # 延迟 import，避免包加载顺序问题
    if strategy_name not in REGISTRY:
        raise KeyError(f"策略 {strategy_name!r} 未登记，可选：{sorted(REGISTRY)}")
    strategy = REGISTRY[strategy_name]
    exit_rule = exit_override if exit_override is not None else strategy.exit

    df, info = load_data(target, start=data_start)
    if info["kind"] == "fund" and isinstance(exit_rule, ExitSpec) and exit_rule.min_hold < 5:
        import dataclasses
        exit_rule = dataclasses.replace(exit_rule, min_hold=5)
        print("※ 基金模式：min_hold 自动提到 5 个交易日（覆盖 7 个自然日 1.5% 惩罚性赎回费）")
    exit_fn = exit_rule.to_fn() if isinstance(exit_rule, ExitSpec) else exit_rule
    exit_desc = exit_rule.describe() if isinstance(exit_rule, ExitSpec) else \
        getattr(exit_rule, "__name__", "自定义离场函数")
    if exit_override is not None:
        exit_desc += "（EXIT_OVERRIDE 覆盖）"

    trades, eq = run_backtest(df, strategy.entry_fn, exit_fn, start=start, cost=cost)
    bt = df.loc[pd.Timestamp(start):]
    n_signals = int(strategy.entry_fn(df).loc[bt.index].sum())
    return print_report(info, strategy, exit_desc, start, cost, n_signals, trades, eq, bt)
