# -*- coding: utf-8 -*-
"""
quant/report_portfolio_parts.py — ⑤ 组合报告的零件（表格 / 明细 / 敏感性）

report_portfolio.py 负责"总装流程"（取数→回测→对照→打印→出图），
本文件负责每一块具体怎么算、怎么打印。拆开的好处：以后想加一块报告
（比如"分年度收益表"）只动这里，总装流程不用碰。
"""

import pandas as pd

from quant import metrics
from quant.data import load_data
from quant.portfolio import run_portfolio_backtest


def get_portfolio(name):
    """配方名 → Portfolio 名片（没登记就明确报错并列出可选项）。"""
    from quant.portfolios import REGISTRY      # 延迟 import，避免包加载顺序问题
    if name not in REGISTRY:
        raise KeyError(f"组合 {name!r} 未登记，可选：{sorted(REGISTRY)}")
    return REGISTRY[name]


def perf_row(eq, label, initial):
    """一行绩效（口径以 Knowledge/metrics.md 为准）。"""
    return {"口径": label,
            "期末金额(元)": round(eq.iloc[-1], 0),
            "总收益": f"{eq.iloc[-1] / initial - 1:+.1%}",
            "年化": f"{metrics.annual_return(eq):+.2%}",
            "最大回撤": f"{metrics.max_drawdown(eq):.1%}",
            "夏普": f"{metrics.sharpe_ratio(eq):.2f}",
            "卡玛": f"{metrics.calmar_ratio(eq):.2f}"}


def load_bench(bench, eq):
    """基准对齐到组合的交易日并缩放到同一起点金额（不能比就返回 None）。"""
    if not bench:
        return None
    try:
        df, _info = load_data(bench, start=str(eq.index[0].date()))
    except Exception as e:                       # 基准取不到不该让整个实验失败
        print(f"⚠ 基准 {bench} 取数失败（{type(e).__name__}: {e}），本次不做基准对比")
        return None
    s = df["close"].reindex(eq.index).ffill().dropna()
    return s / s.iloc[0] * eq.iloc[0]


def print_trades(log, initial, cost, eq):
    """成交明细：第一行是建仓，之后每一行是一次再平衡（带方向 + 上一段分腿盈亏）。"""
    open_day = eq.attrs.get("建仓日")
    n_rebal = max(len(log) - 1, 0)               # 建仓不算调仓
    print(f"\n建仓 {open_day:%Y-%m-%d}（起点后第一个交易日成交，T+1 纪律）；"
          f"再平衡 {n_rebal} 次，总成本 {eq.attrs['总成本']:.1f} 元"
          f"（占本金 {eq.attrs['总成本'] / initial:.2%}）")
    if not n_rebal:
        return
    print("再平衡明细（日期 / 成交额 / 买卖金额 +买 −卖 / 距上次调仓这段各腿赚亏）：")
    for _, r in log.iloc[1:].iterrows():
        moves = " ".join(f"{c[3:]}{v:+.0f}" for c, v in r.items()
                         if c.startswith("调仓-") and abs(v) > 1)
        # 贡献-X = 上次调仓到本次调仓之间 X 这条腿的持有损益（引擎逐日记的账）
        gains = " ".join(f"{c[3:]}{v:+.0f}" for c, v in r.items()
                         if c.startswith("贡献-") and abs(v) > 1)
        print(f"  {r['日期']:%Y-%m-%d}  成交 {r['成交总额']:.0f} 元  [{moves}]"
              + (f"  段内盈亏[{gains}]" if gains else ""))
    gaps = log["日期"].diff().dt.days.dropna()
    n_short = int((gaps < 7).sum())
    if n_short:
        # 场外基金持有 <7 天赎回吃 1.5% 惩罚费，本回测按 0.1% 简化 → 差额未计入
        print(f"⚠ 间隔 <7 天的调仓 {n_short} 次：实盘中这些赎回按 1.5% 惩罚费率计，"
              f"本回测按 {cost:.1%} 简化（每笔差额约几元，金额小但纪律上要知道）")


def print_weights(weights):
    """权重漂移范围：教学重点——「不干预的话仓位会歪成什么样」。"""
    print("权重漂移范围（若不再平衡会歪到哪）：")
    for n in weights.columns:
        print(f"  {n}: {weights[n].min():.1%} ~ {weights[n].max():.1%}")


def threshold_sensitivity(navs, decide_fn, start, cost, initial,
                          values=(0.02, 0.03, 0.05, 0.10)):
    """阈值敏感性：用同一个决策工厂换参数重跑，看结论是否依赖那个参数点。

    能扫的前提是决策函数带 factory/params 标签（rebalance.py 的工厂都带）；
    自定义决策函数没标签就跳过——跳过时明确说，不假装扫过了。
    """
    factory = getattr(decide_fn, "factory", None)
    params = getattr(decide_fn, "params", None)
    if factory is None or not params or "threshold" not in params:
        print("（决策函数无 threshold 参数或非工厂生成 → 跳过阈值敏感性扫描）")
        return None
    rows = []
    for th in values:
        fn = factory(**{**params, "threshold": th})
        eq, _w, log = run_portfolio_backtest(navs, fn, start=start, cost=cost,
                                             initial_cash=initial)
        rows.append({"阈值": f"{th:.0%}", "再平衡次数": max(len(log) - 1, 0),
                     "年化": f"{metrics.annual_return(eq):+.2%}",
                     "最大回撤": f"{metrics.max_drawdown(eq):.1%}",
                     "夏普": f"{metrics.sharpe_ratio(eq):.2f}"})
    tbl = pd.DataFrame(rows).set_index("阈值")
    print(f"\n参数敏感性（阈值扰动，其余不变）：\n{tbl.to_string()}")
    print("读法：若年化随阈值剧烈变化 → 原文那个参数是「调出来的」（过拟合）；"
          "变化温和 → 结论不依赖参数点")
    return tbl
