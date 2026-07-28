# -*- coding: utf-8 -*-
"""
test_portfolio.py — 组合引擎自检（plans/16 建引擎、plans/17 换成决策函数契约）

跑法：python test_portfolio.py    全绿才算这套组合回测可信。
每一项都在防一类具体的错，不是凑数：
① 账目守恒  ② 再平衡真把权重拉回目标  ③ T 日决策 → T+1 成交（防未来函数）
④ 成本真扣  ⑤ 起点校验  ⑥ 权重校验  ⑦ 不许透支/裸卖空  ⑧ 决策函数看不到未来
⑨ 组合注册表可用（run.py 填名字就能跑的前提）  ⑩ 分腿收益归因守恒（plans/23）
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
import numpy as np
import pandas as pd

from quant.portfolio import run_portfolio_backtest
from quant.rebalance import buy_and_hold, threshold_rebalance

idx = pd.date_range("2024-01-02", periods=60, freq="B")
# A: 每天 +1%；B: 前 30 天 -1%/天，后 30 天 +2%/天 —— 权重必然漂移
a = pd.DataFrame({"close": 100 * np.cumprod([1.01] * 60)}, index=idx)
b = pd.DataFrame({"close": 100 * np.cumprod([0.99] * 30 + [1.02] * 30)}, index=idx)
nav = {"A": a, "B": b}
W = {"A": 0.5, "B": 0.5}
INIT = 10000.0

# ① 账目守恒：无成本 + 买入持有，净值必须等于手算的加权净值
#    注意建仓在**第二个交易日**成交（T 日下单 T+1 成交），所以从 index[1] 起对齐
eq, wts, log = run_portfolio_backtest(nav, buy_and_hold(W), cost=0.0, initial_cash=INIT)
manual = INIT * (0.5 * a["close"] / a["close"].iloc[1] + 0.5 * b["close"] / b["close"].iloc[1])
assert np.allclose(eq.iloc[1:].values, manual.iloc[1:].values, atol=1e-8), "买入持有账目不平"
assert abs(eq.iloc[0] - INIT) < 1e-9, "第一天应还是现金 10000"
assert len(log) == 1, f"买入持有应只有 1 次成交（建仓），实际 {len(log)}"
print(f"① 账目守恒 ✓（建仓 {log['日期'].iloc[0]:%m-%d}，期末权重 "
      f"{wts.iloc[-1].round(3).to_dict()}）")

# ② 再平衡拉回目标：每个调仓日收盘后权重应回到 50/50
eq2, wts2, log2 = run_portfolio_backtest(nav, threshold_rebalance(W, threshold=0.03),
                                         cost=0.0, initial_cash=INIT)
rebal2 = log2.iloc[1:]                                   # 去掉建仓那一行
assert len(rebal2) > 0, "60 天里漂移这么大居然一次都没触发再平衡？"
dev = (wts2.loc[rebal2["日期"]] - 0.5).abs().max().max()
assert dev < 0.005, f"调仓后权重偏离 50/50 太多: {dev}"
print(f"② 再平衡 {len(rebal2)} 次，调仓后权重最大偏差 {dev:.5f} ✓")

# ③ T+1 成交（核心防未来函数）：权重极差首次 ≥3% 的**次日**才允许出现在成交日志里
spread = wts2.max(axis=1) - wts2.min(axis=1)
t0 = spread[spread >= 0.03].index[0]
t1 = wts2.index[wts2.index.get_loc(t0) + 1]
assert rebal2["日期"].iloc[0] == t1, f"应在 {t1} 成交，实际 {rebal2['日期'].iloc[0]}"
print(f"③ T 日触发 → T+1 成交 ✓（{t0:%m-%d} 触发 → {t1:%m-%d} 成交）")

# ④ 成本真扣：0.1% 成本的期末必须严格低于无成本版
eq3, _, log3 = run_portfolio_backtest(nav, threshold_rebalance(W, threshold=0.03),
                                      cost=0.001, initial_cash=INIT)
assert eq3.iloc[-1] < eq2.iloc[-1], "有成本反而赚更多？"
print(f"④ 成本生效 ✓（总成本 {eq3.attrs['总成本']:.2f} 元，期末 "
      f"{eq2.iloc[-1]:.0f} → {eq3.iloc[-1]:.0f}）")

# ⑤ 起点校验：某成分晚上市，start 早于"全员就绪日"必须报错（不许静默晚开始）
c = pd.DataFrame({"close": 100 * np.cumprod([1.005] * 30)}, index=idx[30:])
try:
    run_portfolio_backtest({"A": a, "C": c}, buy_and_hold(), start="2024-01-02")
    raise SystemExit("⑤ 起点校验失效！")
except ValueError as e:
    print(f"⑤ 起点校验 ✓（{e}）")

# ⑥ 权重合计校验
try:
    run_portfolio_backtest(nav, buy_and_hold({"A": 0.6, "B": 0.6}))
    raise SystemExit("⑥ 权重校验失效！")
except ValueError:
    print("⑥ 权重合计≠1 报错 ✓")

# ⑦ 不许透支/裸卖空：决策函数狮子大开口，引擎必须自动截断
def greedy_buy(ctx):
    """天天想各买 100 万（账上只有 1 万）→ 只能按现金成交，不许借钱。"""
    return {"A": 1e6, "B": 1e6}

eq7, wts7, log7 = run_portfolio_backtest(nav, greedy_buy, cost=0.001, initial_cash=INIT)
assert (eq7 > 0).all(), "净值出现非正数 → 账目算炸了"
assert (wts7.sum(axis=1) <= 1 + 1e-9).all(), "权重合计 >100% → 用了杠杆"
ceiling = INIT * a["close"].iloc[-1] / a["close"].iloc[1]      # 全仓买最强的那只的上限
assert eq7.iloc[-1] <= ceiling + 1e-6, f"没借钱却赚过了全仓上限 {ceiling:.0f}"

def greedy_sell(ctx):
    """第一天正常建仓，之后天天想各卖 100 万 → 最多卖光，不许卖成负数。"""
    return {"A": 5000, "B": 5000} if ctx.i == 0 else {"A": -1e6, "B": -1e6}

eq8, wts8, log8 = run_portfolio_backtest(nav, greedy_sell, cost=0.001, initial_cash=INIT)
assert (wts8 >= -1e-12).all().all(), "出现负权重 → 裸卖空了"
assert wts8.iloc[-1].sum() < 1e-9, "清仓日之后应全是现金"
assert len(log8) == 2, f"只该有建仓 + 一次清仓两笔成交，实际 {len(log8)}（卖空单没被拦住）"
assert abs(eq8.iloc[-1] - eq8.iloc[3]) < 1e-9, "清仓后净值还在波动？说明还持着仓"
print(f"⑦ 买不超现金（上限 {ceiling:.0f}，实得 {eq7.iloc[-1]:.0f}）、"
      f"卖不超持仓（清仓后 {eq8.iloc[-1]:.0f} 元现金不再变动）✓")

# ⑧ 决策函数看不到未来：ctx.hist 的最后一行必须就是决策日本身
seen = []
def spy(ctx):
    seen.append((ctx.date, ctx.hist.index[-1], len(ctx.hist)))
    return None

run_portfolio_backtest(nav, spy, initial_cash=INIT)
assert all(d == last for d, last, _ in seen), "ctx.hist 里出现了决策日之后的数据！"
assert [n for _, _, n in seen] == list(range(1, len(seen) + 1)), "ctx.hist 长度不是逐日递增"
print(f"⑧ 决策函数只看得到当日及以前 ✓（{len(seen)} 天逐一核对）")

# ⑨ 组合注册表：所有配方都能 import、名字不与单标的策略撞、决策函数可调用
from quant.portfolios import REGISTRY
from quant.strategies import REGISTRY as STRATS

assert REGISTRY, "组合注册表是空的"
assert not (set(REGISTRY) & set(STRATS)), "组合名与策略名撞车 → run.py 分不清模式"
for name, p in REGISTRY.items():
    assert p.name == name, f"{name} 的 name 字段与注册键不一致"
    assert len(p.holdings) >= 1, f"{name} 没有成分"
    # 注意：这里**不要求** ≥2 个成分。区分两个契约的标准是"输出形状"而不是"几只标的"：
    # 择时策略输出 True/False（满仓/空仓），组合策略输出每只的买卖金额（可分批、可留现金）。
    # 所以 grid_3tier 这种"单标的分批建仓 + 留现金"的网格，天然属于组合库（见
    # Knowledge/strategy_translation.md 的决策树）。
    assert callable(p.decide_fn), f"{name} 的 decide_fn 不可调用"
    # 用假数据跑 5 天，确认决策函数签名对得上（不下载真数据，纯契约检查）
    fake = {k: pd.DataFrame({"close": np.linspace(1, 1.1, 40)}, index=idx[:40])
            for k in p.holdings}
    e, w, l = run_portfolio_backtest(fake, p.decide_fn, initial_cash=INIT)
    # 权重和 ≤1：留现金的策略（网格未启动时是空仓）合法，>1 才是账目出错（透支/卖空）
    assert len(e) == 40 and -1e-9 <= w.iloc[-1].sum() <= 1 + 1e-6, f"{name} 跑不通"
print(f"⑨ 组合注册表 {len(REGISTRY)} 个配方全部可跑 ✓（{', '.join(REGISTRY)}）")

# ⑩ 分腿归因：引擎记的每腿损益必须与账目守恒，且成交日志里的分段贡献要拼得起来
#    （这是"钱是谁赚的"这张表能不能信的唯一依据；对不上宁可报错也不出图）
from quant.attribution import cum_contrib, daily_contrib

eqA, wA, logA = run_portfolio_backtest(nav, threshold_rebalance(W, threshold=0.03),
                                       cost=0.001, initial_cash=INIT)
contrib = daily_contrib(eqA, wA, logA)          # 内部已断言 Σ各腿−成本 == 总资产变化
total_pnl = eqA.iloc[-1] - INIT
by_leg = contrib[["A", "B"]].sum().sum() - contrib["成本"].sum()
assert abs(by_leg - total_pnl) < 1e-8, f"分腿贡献合计 {by_leg:.6f} ≠ 总盈亏 {total_pnl:.6f}"
# 现金不生息：任何一天都不该有"现金腿"凭空生出损益 → 上面的守恒已覆盖，这里查累计线
cum = cum_contrib(contrib)
assert abs(cum["合计"].iloc[-1] - total_pnl) < 1e-8, "累计贡献线终点 ≠ 总盈亏（图会画错）"
# 成交日志的分段贡献：各行相加 = 首日到最后一次成交日之间的分腿损益（尾段不在日志里）
last_trade = logA["日期"].iloc[-1]
for n in ("A", "B"):
    from_log = logA[f"贡献-{n}"].sum()
    from_daily = contrib.loc[:last_trade, n].sum()
    assert abs(from_log - from_daily) < 1e-8, \
        f"{n} 的日志分段贡献 {from_log:.6f} 与逐日损益 {from_daily:.6f} 拼不上"
# 建仓那一行贡献必须是 0（建仓前全是现金，不可能已经赚到钱）
assert abs(logA[["贡献-A", "贡献-B"]].iloc[0].abs().sum()) < 1e-12, "建仓日就有持有损益？"
print(f"⑩ 分腿归因守恒 ✓（A{contrib['A'].sum():+.0f} B{contrib['B'].sum():+.0f} "
      f"成本{-contrib['成本'].sum():+.0f} = 总盈亏{total_pnl:+.0f} 元；"
      f"{len(logA)} 行日志分段贡献可拼接）")

print("\n全部通过")
