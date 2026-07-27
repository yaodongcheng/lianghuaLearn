# -*- coding: utf-8 -*-
"""
quant/plot.py — ⑤ 评估层伴侣：回测买卖点标注图（run.py 每次自动产出）

图面约定（教学导向）：
- 上图：收盘价曲线；红▲=买入成交；▼=卖出成交，**红/绿=盈/亏（A股配色）**，
  旁注"卖出原因+收益率"；持仓段底色同胜负（淡红盈/淡绿亏）
- 灰点=信号但未成交（被持仓期/冷却期挡住——"这里为啥没买"一看就懂）
- 下图：策略净值（红）vs 买入持有（灰），虚线标最大回撤的峰→谷
- 红涨绿跌中国配色；中文字体 SimHei/微软雅黑双保险（与 wheels.md K 线样式同口径）
"""
import matplotlib
matplotlib.use("Agg")   # 无界面后端：只存 PNG 不弹窗（与 plot_kline.py 同约定）
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D

from fetch_data import DATA_DIR
from quant import metrics
from quant.data import load_data
from quant.engine import run_backtest_ex
from quant.exits import ExitSpec, adjust_for_fund

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False   # 负号用 ASCII，防字体缺方块


def _win_color(ret):
    """收益率 → 红盈绿亏（A股配色，用户指定语义：颜色通道给胜负，原因放标注文字）。"""
    return "red" if ret > 0 else "green"


def _price_panel(ax, bt, trades, tail, sig, annotate=True, legend=True):
    """价格子图（单策略图与比选图共用，保证两种图"说同一种语言"）：
    收盘线 + 持仓段底色（红盈绿亏）+ 买▲/卖▼（旁注原因+收益率）+ 未成交信号灰点。
    返回被挡信号数（图例用）。比选模式可关掉 annotate/legend 省空间。"""
    ax.plot(bt.index, bt["close"], color="0.25", linewidth=1, label="收盘价")
    blocked = 0
    for d in sig[sig].index:                 # 信号灰点：次日没变成买入 = 被持仓/冷却挡住
        i = bt.index.get_loc(d)
        nxt = bt.index[i + 1] if i + 1 < len(bt) else None
        if nxt is None or str(nxt.date()) not in set(trades["买入日"]):
            ax.scatter(d, bt.loc[d, "close"] * 0.94, marker="o", color="0.6", s=18)
            blocked += 1
    for k, (_, t) in enumerate(trades.iterrows()):   # 持仓段 + 买▲ + 卖▼（红盈绿亏）
        d0, d1 = pd.Timestamp(t["买入日"]), pd.Timestamp(t["卖出日"])
        color = _win_color(t["收益率"])
        ax.axvspan(d0, d1, color=color, alpha=0.07)
        ax.scatter(d0, bt.loc[d0, "close"] * 0.97, marker="^", color="red", s=70, zorder=5)
        y = bt.loc[d1, "close"] * 1.03
        ax.scatter(d1, y, marker="v", color=color, s=70, zorder=5)
        if annotate:
            frac = (d1 - bt.index[0]).days / max((bt.index[-1] - bt.index[0]).days, 1)
            ha = "left" if frac < 0.06 else ("right" if frac > 0.94 else "center")  # 贴边防裁剪
            ax.annotate(f"{t['卖出原因']}{t['收益率']:+.1%}", (d1, y), ha=ha, va="bottom",
                        xytext=(0, 6 + 9 * (k % 2)), textcoords="offset points",
                        fontsize=8, color=color, zorder=6)
    if tail.get("position") is not None:     # 期末仍持仓：底色画到末日并如实标注
        p = tail["position"]
        ax.axvspan(p.entry_date, bt.index[-1], color=_win_color(tail["unrealized"] or 0),
                   alpha=0.07)
        ax.scatter(p.entry_date, bt.loc[p.entry_date, "close"] * 0.97, marker="^",
                   color="red", s=70, zorder=5)
        ax.annotate(f"持仓中 浮盈{tail['unrealized']:+.1%}", (bt.index[-1],
                    bt["close"].iloc[-1] * 1.03), ha="right", fontsize=9,
                    color=_win_color(tail["unrealized"] or 0))
    if legend:
        ax.legend(handles=[Line2D([], [], marker="^", color="red", ls="", label="买入"),
                           Line2D([], [], marker="v", color="red", ls="", label="卖出·盈利"),
                           Line2D([], [], marker="v", color="green", ls="", label="卖出·亏损"),
                           Line2D([], [], marker="o", color="0.6", ls="",
                                  label=f"信号未成交×{blocked}（持仓/冷却中）")],
                  loc="upper left", bbox_to_anchor=(0.0, 0.87), fontsize=8)  # 左上空白区，防压右侧标注
    ax.grid(True, linestyle="-.", alpha=0.4)
    return blocked


def plot_trades(bt, trades, eq, tail, sig, title, out_png):
    """核心画图函数：bt=回测区间 df（date 索引）；trades/eq/tail=引擎产物；sig=区间信号列。"""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1]})
    _price_panel(ax1, bt, trades, tail, sig)
    s = metrics.summarize(trades, eq)
    win = f"{s['胜率']:.0%}" if s["交易数"] else "—"
    ax1.text(0.01, 0.97, f"{s['交易数']}笔 胜率{win} 年化{s['年化']:+.1%} "
             f"最大回撤{s['最大回撤']:+.1%}", transform=ax1.transAxes, va="top",
             fontsize=10, bbox=dict(fc="white", ec="0.8", alpha=0.9))
    ax1.set_title(title, fontsize=12)

    ax2.plot(eq.index, eq.values, color="red", linewidth=1.2, label="策略净值")
    ax2.plot(bt.index, (bt["close"] / bt["close"].iloc[0]).values, color="0.6",
             linewidth=0.8, label="买入持有")
    dd = eq / eq.cummax() - 1                # 最大回撤的峰→谷虚线（metrics.md §2 口径）
    trough = dd.idxmin()
    ax2.axvline(eq.loc[:trough].idxmax(), ls=":", color="0.5")
    ax2.axvline(trough, ls=":", color="0.5")
    ax2.annotate(f"最大回撤 {dd.min():+.1%}", (trough, eq.loc[trough]), fontsize=8,
                 xytext=(5, -12), textcoords="offset points")
    ax2.legend(loc="upper left", fontsize=8)
    ax2.grid(True, linestyle="-.", alpha=0.4)

    fig.tight_layout()
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print(f"📊 买卖点标注图已保存：{out_png}")
    return out_png


def plot_experiment(target, strategy_name, start, exit_override=None,
                    data_start="20180101", cost=0.001):
    """run.py 出图入口：与 run_experiment 同参数口径（重算一遍，缓存+引擎毫秒级）。"""
    from quant.strategies import REGISTRY
    st = REGISTRY[strategy_name]
    rule = exit_override if exit_override is not None else st.exit
    df, info = load_data(target, start=data_start)
    rule = adjust_for_fund(rule, info["kind"])   # 基金防惩罚费（exits.py 统一收口）
    exit_fn = rule.to_fn() if isinstance(rule, ExitSpec) else rule
    desc = rule.describe() if isinstance(rule, ExitSpec) else \
        getattr(rule, "__name__", "自定义离场")
    trades, eq, tail = run_backtest_ex(df, st.entry_fn, exit_fn, start=start, cost=cost)
    bt = df.loc[pd.Timestamp(start):]
    title = (f"{info['name']} × {strategy_name}｜{desc}｜"
             f"{bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}")
    return plot_trades(bt, trades, eq, tail, st.entry_fn(df).loc[bt.index],
                       title, DATA_DIR / f"trades_{info['code']}_{strategy_name}.png")
