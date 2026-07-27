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
from quant.engine import run_backtest, run_backtest_ex
from quant.exits import ExitSpec, adjust_for_fund


def sample_warnings(n_trades, n_params):
    """样本量/参数数警报：8 年 9 笔的"胜率 89%"和 900 笔的不是一回事。"""
    if n_trades < 30:
        print(f"⚠ 样本量警报：仅 {n_trades} 笔交易（<30），统计置信度低，"
              f"期望收益请按区间理解，别按点估计理解")
    if n_params > 4:
        print(f"⚠ 参数数警报：{n_params} 个参数（>4），过拟合风险高，"
              f"先做 param_sweep 扰动测试再下结论")


def print_report(info, strategy, exit_desc, start, cost, n_signals, trades, eq, bt, tail=None):
    """单策略完整报告：三要素回显 → 汇总指标 → 逐笔明细。
    tail 是 run_backtest_ex 给的期末状态：用于把"期末仍持仓/信号待成交"如实写出，
    不传则按老行为只区分有无闭环交易。"""
    print(f"\n{'=' * 74}\n回测报告：{info['name']}（{info['kind']}:{info['code']}） × 策略「{strategy.name}」\n{'=' * 74}")
    print(f"区间：{bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}    "
          f"离场：{exit_desc}    成本：双边 {cost:.1%}（T 日信号 → T+1 开盘成交）")
    if strategy.note:
        print(f"策略备注：{strategy.note}")

    s = metrics.summarize(trades, eq)
    holding = tail is not None and tail.get("position") is not None
    n_closed = s["交易数"]
    closed_txt = f"闭环 {n_closed} 笔" + ("＋期末持仓中 1 笔" if holding else "")
    # 0 笔闭环时胜率/平均每笔是 0÷0=nan，显示 "—" 而不是 "nan%"（口径与 compare_table 一致）
    win = f"{s['胜率']:.0%}" if n_closed else "—"
    avg = f"{s['平均每笔']:+.1%}" if n_closed else "—"
    pfr = f"{s['盈亏比']:.1f}" if n_closed else "—"
    print(f"\n信号 {n_signals} 次 → {closed_txt}   胜率 {win}   平均每笔 {avg}（盈亏比 {pfr}）")
    print(f"总收益 {s['总收益']:+.1%}   年化 {s['年化']:+.1%}   最大回撤 {s['最大回撤']:+.1%}   "
          f"夏普 {s['夏普']:.2f}   卡玛 {s['卡玛']:.2f}")
    bh = bt["close"].iloc[-1] / bt["close"].iloc[0] - 1
    print(f"（对照·买入持有：{bh:+.1%}）")
    if info["kind"] in ("a", "hk"):
        print("※ 个股回测未处理涨跌停无法成交（主板 ±10%/创业科创 ±20%），"
              "涉及追涨停/抄底跌停的信号结论需手工复核")
    sample_warnings(n_closed, _count_params(strategy))

    if len(trades):
        t = trades.copy()
        t["收益率"] = (t["收益率"] * 100).round(1).astype(str) + "%"
        print(f"\n逐笔明细：\n{t.to_string(index=False)}")

    if holding:
        p = tail["position"]
        print(f"\n※ 期末仍持仓（未计入上方统计）：{p.entry_date:%Y-%m-%d} 买入 "
              f"@ {p.entry_price:,.2f}，持有 {p.hold_days} 个交易日，"
              f"浮盈 {tail['unrealized']:+.1%}（按 {bt.index[-1]:%Y-%m-%d} 收盘估值，离场条件均未触发）")
    elif tail is not None and tail.get("pending_buy"):
        print("\n※ 最后交易日收盘刚触发信号，T+1 行情尚未发生，等待成交")
    elif not len(trades):
        if n_signals == 0:
            print("\n无交易：区间内信号从未触发（策略全程空仓观望）")
        else:
            print(f"\n无交易：{n_signals} 次信号均落在持仓期/冷却期内，未形成新买入")
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
        fn = lambda df, _p=params: make_signal(df, **_p)   # 参数绑进入场函数（防闭包晚绑定）
        trades, eq = run_backtest(df, fn, exit_fn, start=start, cost=cost)
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
    exit_rule = adjust_for_fund(exit_rule, info["kind"])   # 基金防惩罚费（exits.py 统一收口）
    exit_fn = exit_rule.to_fn() if isinstance(exit_rule, ExitSpec) else exit_rule
    exit_desc = exit_rule.describe() if isinstance(exit_rule, ExitSpec) else \
        getattr(exit_rule, "__name__", "自定义离场函数")
    if exit_override is not None:
        exit_desc += "（EXIT_OVERRIDE 覆盖）"

    trades, eq, tail = run_backtest_ex(df, strategy.entry_fn, exit_fn, start=start, cost=cost)
    bt = df.loc[pd.Timestamp(start):]
    n_signals = int(strategy.entry_fn(df).loc[bt.index].sum())
    return print_report(info, strategy, exit_desc, start, cost, n_signals, trades, eq, bt, tail)
