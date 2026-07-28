# -*- coding: utf-8 -*-
"""
quant/plot_portfolio.py — ⑤ 组合版图表（与 plot.py / plot_compare.py 同族）

单配方图（四联，上下共享时间轴）：
    ①：归一化净值——本策略 / 不再平衡对照 / 各成分 / 基准（谁强谁弱一眼看出）
    ②：各成分权重随时间 + 目标线 + ▼ 再平衡点（"仓位歪了又被拉回来"的过程）
    ③：各成分**累计贡献金额**（元）——"这些钱是哪条腿赚的"，含成本与合计校验线
    ④：相对对照组的超额（本策略净值 ÷ 不再平衡净值 − 1）——再平衡的净贡献曲线，
        0 上方=再平衡赚了，下方=白折腾

② 和 ③ 要连着看：②说"钱放在哪"，③说"钱从哪赚回来"。动态持仓的组合里两者
经常错位——涨最猛的腿被再平衡一路减仓，贡献未必最大（见 plans/23）。

比选图（多配方）：共享净值 + 相对基准超额，图例自带年化/回撤。
"""
import matplotlib

matplotlib.use("Agg")          # 无界面后端：只存 PNG（与 plot.py 同约定）
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

from fetch_data import DATA_DIR
from quant import metrics
from quant.plot_attribution import panel_cum_contrib

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

_norm = lambda s: s / s.iloc[0]


def plot_portfolio_experiment(name, eq, eq_hold, navs, weights, log, bench_eq,
                              bench_name="沪深300", desc="", target_weights=None):
    """单配方四联图。返回 PNG 路径（固定文件名，重跑覆盖更新）。"""
    fig, (ax1, ax2, ax4, ax3) = plt.subplots(4, 1, figsize=(13.5, 14), sharex=True,
                                             gridspec_kw={"height_ratios": [3, 2, 2, 1.6]})

    ax1.plot(eq.index, _norm(eq), color="red", lw=2,
             label=f"本策略（年化{metrics.annual_return(eq):+.1%} "
                   f"回撤{metrics.max_drawdown(eq):.1%}）")
    ax1.plot(eq_hold.index, _norm(eq_hold), color="orange", lw=1.3, alpha=0.9,
             label=f"不再平衡对照（年化{metrics.annual_return(eq_hold):+.1%} "
                   f"回撤{metrics.max_drawdown(eq_hold):.1%}）")
    for n, df in navs.items():                       # 各成分单买的表现
        s = df["close"].reindex(eq.index).ffill().dropna()
        ax1.plot(s.index, _norm(s), lw=0.9, alpha=0.6, label=n)
    if bench_eq is not None:
        ax1.plot(bench_eq.index, _norm(bench_eq), color="0.4", lw=1.2, ls="--",
                 label=f"{bench_name}（年化{metrics.annual_return(bench_eq):+.1%} "
                       f"回撤{metrics.max_drawdown(bench_eq):.1%}）")
    for d in (log["日期"].iloc[1:] if len(log) > 1 else []):
        ax1.axvline(d, color="purple", alpha=0.2, lw=0.8)
    ax1.set_title(f"净值归一化（期初=1）；紫竖线=再平衡日（共 {max(len(log) - 1, 0)} 次）",
                  fontsize=10, loc="left")
    ax1.legend(ncol=3, fontsize=8.5)
    ax1.grid(alpha=0.3)

    for n in weights.columns:
        ax2.plot(weights.index, weights[n], lw=1.1, label=n)
    # 目标权重线：等权时只有一条，自定义权重时每个不同的目标值一条
    targets = sorted(set(round(v, 4) for v in (target_weights or {}).values())) \
        or [round(1 / len(weights.columns), 4)]
    for k, t in enumerate(targets):
        ax2.axhline(t, color="0.5", lw=0.8, ls=":",
                    label=f"目标 {t:.0%}" if k == 0 else None)
    if len(log) > 1:
        ax2.scatter(log["日期"].iloc[1:],
                    [weights.loc[d].max() * 1.02 for d in log["日期"].iloc[1:]],
                    marker="v", color="purple", s=14, alpha=0.55, zorder=5, label="再平衡")
    # y 轴按实际漂移范围缩放（固定 0~0.6 会把所有线挤成一条，看不出漂移）
    lo, hi = weights[weights.sum(axis=1) > 0].min().min(), weights.max().max()
    ax2.set_ylim(max(0.0, lo - 0.02), hi + 0.03)
    ax2.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax2.set_title("各成分权重随时间（▼=再平衡触发后权重被拉回目标）", fontsize=10, loc="left")
    ax2.legend(ncol=6, fontsize=8.5)
    ax2.grid(alpha=0.3)

    excess = eq / eq_hold - 1                         # 再平衡的净贡献
    # ---------- ③ 各成分累计贡献金额（元）：钱是哪条腿赚的（零件在 plot_attribution.py）----
    panel_cum_contrib(ax4, eq, weights, log,
                      mark_dates=log["日期"].iloc[1:] if len(log) > 1 else None)

    # ---------- ④ 再平衡净贡献：本策略 ÷ 不再平衡 − 1 ----------
    ax3.plot(excess.index, excess.values, color="purple", lw=1.2)
    ax3.axhline(0, color="0.4", lw=0.8)
    ax3.fill_between(excess.index, 0, excess.values, where=excess.values >= 0,
                     color="red", alpha=0.15)
    ax3.fill_between(excess.index, 0, excess.values, where=excess.values < 0,
                     color="green", alpha=0.15)
    ax3.set_title(f"再平衡的净贡献（本策略 ÷ 不再平衡 − 1）：期末 {excess.iloc[-1]:+.1%}，"
                  f"{(excess > 0).mean():.0%} 的时间领先对照组", fontsize=10, loc="left")
    ax3.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    ax3.grid(alpha=0.3)

    fig.suptitle(f"组合「{name}」｜{desc}｜{eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}"
                 f"｜期末 {eq.iloc[-1]:,.0f} 元", fontsize=13)
    fig.tight_layout()
    out = DATA_DIR / f"portfolio_{name}.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"📊 组合图已保存：{out}")
    return out


def plot_portfolio_compare(results, bench_eq, bench_name="沪深300"):
    """比选图：results = [(名称, eq, weights, log), ...]，共享净值 + 相对基准超额。"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13.5, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    for n, eq, _w, log in results:
        ax1.plot(eq.index, _norm(eq), lw=1.6,
                 label=f"{n}（年化{metrics.annual_return(eq):+.1%} "
                       f"回撤{metrics.max_drawdown(eq):.1%} 调仓{max(len(log) - 1, 0)}次）")
    if bench_eq is not None:
        ax1.plot(bench_eq.index, _norm(bench_eq), color="0.4", lw=1.2, ls="--",
                 label=bench_name)
    ax1.set_title("组合比选：归一化净值（期初=1，统一起点）", fontsize=10, loc="left")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.3)

    if bench_eq is not None:
        base = _norm(bench_eq)
        for n, eq, _w, _log in results:
            xs = _norm(eq) / base - 1
            ax2.plot(xs.index, xs.values, lw=1.3,
                     label=f"{n}（期末{xs.iloc[-1]:+.1%}｜跑赢{(xs > 0).mean():.0%}时间）")
        ax2.axhline(0, color="0.4", lw=0.8)
        ax2.set_title(f"超额收益（组合净值 ÷ {bench_name}净值 − 1）", fontsize=10, loc="left")
        ax2.legend(fontsize=9)
        ax2.grid(alpha=0.3)

    fig.suptitle(f"组合比选｜{' / '.join(n for n, *_ in results)}", fontsize=13)
    fig.tight_layout()
    out = DATA_DIR / f"portfolio_compare_{'_'.join(n for n, *_ in results)}.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"📊 组合比选图已保存：{out}")
    return out
