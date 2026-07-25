# -*- coding: utf-8 -*-
"""
test_framework.py — plans/07 主测试用例 + 验收测试集

跑什么（对应 plans/07 验收标准）：
  1. ⭐ 主测试用例：框架 vs 归档 v3 引擎逐笔回归（6 信号 × 2 指数 × 4 离场），
     并复现 Knowledge/zhihu/吃超跌恐慌修复策略.md 的 v3 关键数字
  2. 因果性门禁：6 个信号全过 assert_no_lookahead；故意写的坏信号必须被抓（负例）
  3. 数据层契约：无缓存自动下载+体检 / 无法解析明确报错 / prepare 批量预下载
  4. 个股数据（茅台 qfq）直接喂同一引擎
  5. 新策略端到端：ma_cross（金叉入场 + exit_below_ma 离场）跑通完整报告
  6. quant/ 每模块 <150 行

用法：python test_framework.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")

from archive import zhihu_strategy1_oversold_v3 as v3   # 回归基准（归档原版，一行未改）
from quant import ExitSpec, assert_no_lookahead, run_backtest
from quant import metrics, signals
from quant.data import load_data, prepare

START = v3.START          # "2018-07-01"，与 v3 同一回测区间
FAILED = []


def check(name, ok, detail=""):
    print(f"  {'✓' if ok else '✗'} {name}{(' — ' + detail) if detail and not ok else ''}")
    if not ok:
        FAILED.append(name)


def compare_trades(fw, old):
    """逐笔对比：买入日/卖出日/持有天数/卖出原因 完全相等，收益率 1e-12 级相等。"""
    if len(fw) != len(old):
        return f"笔数不同：框架 {len(fw)} vs v3 {len(old)}"
    for col in ["买入日", "卖出日", "持有交易日", "卖出原因"]:
        if not (fw[col].values == old[col].values).all():
            i = int(np.nonzero(fw[col].values != old[col].values)[0][0])
            return f"第 {i + 1} 笔 {col} 不同：框架 {fw[col].iloc[i]} vs v3 {old[col].iloc[i]}"
    if len(fw) and not np.allclose(fw["收益率"], old["收益率"], atol=1e-12):
        return "收益率不一致（>1e-12）"
    return ""


SIGNALS = [("10日跌≥7%", signals.sig_crash), ("RSI6≤20", signals.sig_rsi_oversold),
           ("BIAS20≤-6%", signals.sig_bias_oversold), ("KDJ-D<20", signals.sig_kdj_d_oversold),
           ("破BOLL下轨", signals.sig_boll_lower), ("60日高点回撤≥8%", signals.sig_drawdown)]
PART1_EXIT = dict(take_profit=0.05, max_hold=20)
PART2_EXITS = [("A 固定+5%/20日", dict(take_profit=0.05, max_hold=20)),
               ("B 移动3%/3%/20日", dict(trail_activate=0.03, trail_pct=0.03, max_hold=20)),
               ("C 移动3%/3%/60日", dict(trail_activate=0.03, trail_pct=0.03, max_hold=60)),
               ("D 移动5%/5%/60日", dict(trail_activate=0.05, trail_pct=0.05, max_hold=60))]


def test_regression():
    print("\n===== 1. 主测试用例：框架 vs 归档 v3 逐笔回归 =====")
    dfs = {}
    for target, symbol in [("上证指数", "000001"), ("沪深300", "000300")]:
        df, _ = load_data(target)
        dfs[target] = df
        bt = df.loc[pd.Timestamp(START):]
        v3_sigs = v3.make_signals(df)          # v3 原版信号（全量计算后切片）

        for label, fw_sig in SIGNALS:
            old_t, old_eq = v3.run_backtest(bt, v3_sigs[label], **PART1_EXIT)
            fw_t, fw_eq = run_backtest(df, fw_sig, ExitSpec(**PART1_EXIT).to_fn(), start=START)
            diff = compare_trades(fw_t, old_t)
            if not diff and not np.allclose(fw_eq.values, old_eq.values, atol=1e-12):
                diff = "净值曲线不一致"
            check(f"{target} Part1 {label}（{len(old_t)} 笔）", not diff, diff)

        for sig_label, fw_sig in SIGNALS[:2]:   # Part 2：前两个信号 × 4 种离场
            for ex_label, kw in PART2_EXITS:
                old_t, _ = v3.run_backtest(bt, v3_sigs[sig_label], **kw)
                fw_t, _ = run_backtest(df, fw_sig, ExitSpec(**kw).to_fn(), start=START)
                diff = compare_trades(fw_t, old_t)
                check(f"{target} Part2 {sig_label}×{ex_label}（{len(old_t)} 笔）", not diff, diff)
    return dfs["上证指数"]  # 上证 df 留给后面的测试复用（注意别返回循环变量，那是沪深300）


def test_doc_numbers(df):
    print("\n===== 1b. 复现策略文档 v3 关键数字（上证） =====")
    bt = df.loc[pd.Timestamp(START):]
    for label, fw_sig, expect in [
            ("BIAS20≤-6%", signals.sig_bias_oversold, (9, "89%", "4.6%", "-5.3%")),
            ("10日跌≥7%", signals.sig_crash, (10, "90%", "4.0%", "-5.2%"))]:
        trades, eq = run_backtest(df, fw_sig, ExitSpec(**PART1_EXIT).to_fn(), start=START)
        s = metrics.summarize(trades, eq)
        got = (s["交易数"], f"{s['胜率']:.0%}", f"{s['年化']:.1%}", f"{s['最大回撤']:.1%}")
        check(f"{label}：{got[0]} 笔/胜率 {got[1]}/年化 {got[2]}/回撤 {got[3]}", got == expect,
              f"期望 {expect}")


def test_lookahead(df):
    print("\n===== 2. 因果性门禁（无未来函数） =====")
    for label, fn in SIGNALS:
        try:
            assert_no_lookahead(fn, df)
            check(f"信号 {label} 过门禁", True)
        except AssertionError as e:
            check(f"信号 {label} 过门禁", False, str(e))
    bad = lambda d: d["close"].shift(-1) > d["close"]   # 明天涨→今天买：典型未来函数
    try:
        assert_no_lookahead(bad, df)
        check("负例：shift(-1) 坏信号被抓", False, "门禁没拦住！")
    except AssertionError:
        check("负例：shift(-1) 坏信号被抓", True)


def test_data_contract():
    print("\n===== 3. 数据层契约 =====")
    df, info = load_data("中证500")      # 无缓存 → 自动下载 + 体检（契约第 2 条）
    check("无缓存自动下载（中证500）", len(df) > 1000 and info["kind"] == "idx")
    try:
        load_data("查无此物xyz")
        check("无法解析→明确报错", False, "没报错！")
    except ValueError:
        check("无法解析→明确报错", True)
    try:
        prepare(["上证指数", "沪深300"])
        check("prepare 批量预下载", True)
    except RuntimeError as e:
        check("prepare 批量预下载", False, str(e))


def test_stock_and_new_strategy():
    print("\n===== 4/5. 个股喂同一引擎 + 新策略端到端 =====")
    df, info = load_data("贵州茅台")     # qfq 个股，缓存已有
    trades, eq = run_backtest(df, signals.sig_bias_oversold,
                              ExitSpec(**PART1_EXIT).to_fn(), start=START)
    check("茅台 qfq 直接喂引擎", len(eq) == len(df.loc[pd.Timestamp(START):]),
          f"净值长度 {len(eq)}")
    print(f"  （茅台 bias_oversold：{len(trades)} 笔，年化 {metrics.annual_return(eq):+.1%}——"
          f"超跌策略是个股反面教材预期，跑通即可）")
    from quant.report import run_experiment
    run_experiment("上证指数", "ma_cross", start=START)   # 金叉入场 + 跌破MA20离场
    check("ma_cross 新策略端到端", True)


def test_module_size():
    print("\n===== 6. 模块行数（上限 150 行） =====")
    for f in sorted(Path("quant").rglob("*.py")):
        n = sum(1 for _ in open(f, encoding="utf-8"))
        check(f"{f}：{n} 行", n < 150)


if __name__ == "__main__":
    df_sh = test_regression()
    test_doc_numbers(df_sh)
    test_lookahead(df_sh)
    test_data_contract()
    test_stock_and_new_strategy()
    test_module_size()
    print(f"\n{'=' * 74}")
    if FAILED:
        print(f"✗ 共 {len(FAILED)} 项失败：{FAILED}")
        sys.exit(1)
    print("✓ 全部通过：框架五层（数据/指标/策略/引擎/评估）可信，可复用于新策略")
