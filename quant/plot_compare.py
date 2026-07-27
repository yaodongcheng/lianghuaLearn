# -*- coding: utf-8 -*-
"""
quant/plot_compare.py — ⑤ 比选模式：多策略同跑 + 对比图（run.py 的 STRATEGY 给名单时启用）

图面设计（用户拍板，plans/11）：
- 每个策略一个价格子图（买卖点画在一张上会重叠）——复用 plot._price_panel，
  与单策略图说同一种语言（红▲买 / 红绿▼卖 / 灰点信号未成交 / 底色持仓段）
- 所有策略的净值放进同一个底部子图（对比才有意义）+ 买入持有灰线做基准；
  净值图例自带"年化/回撤"，眼睛不用来回切换就能读出谁强谁弱
"""
import matplotlib
matplotlib.use("Agg")   # 无界面后端：只存 PNG（与 plot.py 同约定）
import matplotlib.pyplot as plt
import pandas as pd

from fetch_data import DATA_DIR
from quant import metrics
from quant.data import load_data
from quant.engine import run_backtest_ex
from quant.exits import ExitSpec, adjust_for_fund
from quant.plot import _price_panel


def plot_compare_experiment(target, strategy_names, start, exit_override=None,
                            data_start="20180101", cost=0.001):
    """多策略比选入口：文字对比表（复用 report.compare_table）+ 对比图 PNG。"""
    from quant.report import compare_table      # 延迟 import：report 与 plot 互为兄妹模块
    from quant.strategies import REGISTRY
    df, info = load_data(target, start=data_start)
    bt = df.loc[pd.Timestamp(start):]
    results = []                                # (策略名, trades, eq, tail, sig)
    for name in strategy_names:
        st = REGISTRY[name]
        rule = adjust_for_fund(exit_override if exit_override is not None else st.exit,
                               info["kind"])
        exit_fn = rule.to_fn() if isinstance(rule, ExitSpec) else rule
        trades, eq, tail = run_backtest_ex(df, st.entry_fn, exit_fn, start=start, cost=cost)
        results.append((name, trades, eq, tail, st.entry_fn(df).loc[bt.index]))
    compare_table(f"策略比选：{info['name']}（{bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}）",
                  [(name, None, t, eq) for name, t, eq, _tail, _s in results])
    out = DATA_DIR / f"compare_{info['code']}_{'_'.join(strategy_names)}.png"
    return _compare_chart(bt, results, info["name"], out)


def _compare_chart(bt, results, target_name, out_png):
    """n 个策略价格子图（各自买卖点）+ 底部共享净值图（绩效写进图例）。"""
    n = len(results)
    fig, axes = plt.subplots(n + 2, 1, figsize=(14, 3.2 * n + 5.2), sharex=True,
                             gridspec_kw={"height_ratios": [3] * n + [2, 2]})
    for i, (ax, (name, trades, eq, tail, sig)) in enumerate(zip(axes[:n], results)):
        _price_panel(ax, bt, trades, tail, sig, legend=(i == 0))
        s = metrics.summarize(trades, eq)
        win = f"{s['胜率']:.0%}" if s["交易数"] else "—"
        ax.set_title(f"{name}：{s['交易数']}笔 胜率{win} 年化{s['年化']:+.1%} "
                     f"最大回撤{s['最大回撤']:+.1%}", fontsize=10, loc="left")
    ax_eq = axes[n]
    for name, trades, eq, _tail, _sig in results:
        s = metrics.summarize(trades, eq)
        ax_eq.plot(eq.index, eq.values, linewidth=1.2,
                   label=f"{name}（年化{s['年化']:+.1%} 回撤{s['最大回撤']:+.1%}）")
    ax_eq.plot(bt.index, (bt["close"] / bt["close"].iloc[0]).values, color="0.6",
               linewidth=0.8, label="买入持有")
    ax_eq.legend(loc="upper left", fontsize=8)
    ax_eq.grid(True, linestyle="-.", alpha=0.4)
    ax_xs = axes[n + 1]                         # 超额收益：策略净值 ÷ 大盘净值 − 1
    bh = bt["close"] / bt["close"].iloc[0]      # 0 上方=跑赢，下方=跑输；颜色与净值图自动同序
    for name, trades, eq, _tail, _sig in results:
        xs = eq / bh - 1
        ax_xs.plot(xs.index, xs.values, linewidth=1.2,
                   label=f"{name}（期末{xs.iloc[-1]:+.1%}｜跑赢{(xs > 0).mean():.0%}时间）")
    ax_xs.axhline(0, color="0.4", linewidth=0.8)
    ax_xs.legend(loc="upper left", fontsize=8)
    ax_xs.grid(True, linestyle="-.", alpha=0.4)
    ax_xs.set_title("超额收益（策略净值 ÷ 大盘净值 − 1）", fontsize=10, loc="left")
    fig.suptitle(f"{target_name} × 策略比选（{' / '.join(name for name, *_ in results)}）｜"
                 f"{bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"📊 策略比选图已保存：{out_png}")
    return out_png
