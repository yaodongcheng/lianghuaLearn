# -*- coding: utf-8 -*-
"""analyze_tencent_exit.py — 计划05：腾讯（00700.HK）卖出时机分析（可重跑）

背景：用户持有腾讯股权激励 233 股，只能卖不能买。本脚本把模糊的"什么时候卖"
变成可执行的规则对比，回答三个问题：
  A. 现在处于什么趋势位置？（均线/近一年区间/距高点回撤）
  B. 几种卖出规则在历史上分别是什么结果？（2010 年以来每个起始日都模拟一遍）
  C. 如果今天开始执行，每条规则具体怎么做？

⭐ 重要定位（plans/05）：这是一次性卖出决策的辅助分析，不是交易策略。
量化只能提供规则与概率，不能预测股价；"精确逃顶"不可信。

口径与防未来函数约定（对照 Knowledge/backtest_checklist.md §1）：
- 所有规则" T 日收盘判断 → T+1 开盘价成交"（收盘后才知道收盘价，当天来不及卖）
- 移动止盈的峰值锚从起始日当天算起（只用持仓期间数据）
- 前复权数据：历史绝对价位与行情软件略有差异（扣了分红），但比率不受影响
- 参数一律平庸整数（3 批/20 日、MA60、回撤 15%），并做邻域扰动（§2 过拟合检查）
- 卖出成本（佣金/平台费）金额固定且很小，不建模，结论里注明
产出：终端一页纸结论 + data/tencent_exit_00700.png（近一年 K 线+均线+关键位）
"""
import sys

import matplotlib
matplotlib.use("Agg")                      # 只存 PNG 不弹窗（项目统一约定）
import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from fetch_data import DATA_DIR
from quant.data import load_data
from quant.indicators import cal_ma

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

SHARES = 233                               # 用户持有的腾讯股数
FORWARD_MIN = 250                          # 情景起点之后至少要有 250 个交易日（约一年）才算有效样本
CANON = [("ladder", 3, 20), ("ma", 60), ("trail", 0.15)]   # 三条候选规则（基准参数）
RULE_NAMES = {("ladder", 3, 20): "分3批·每月一批",
              ("ma", 60): "跌破MA60全卖",
              ("trail", 0.15): "峰值回撤15%卖"}
# 参数扰动名单：看结论方向是否在邻域参数上稳定（平台而非尖刺才可信）
VARIANTS = [("ladder", 2, 20), ("ladder", 3, 20), ("ladder", 4, 20),
            ("ma", 40), ("ma", 60), ("ma", 80),
            ("trail", 0.10), ("trail", 0.15), ("trail", 0.20)]


# ---------------------------------------------------------------- 规则模拟
def simulate(rule, t0, closes, opens, mas):
    """从起始日 t0（整数位置）模拟一条卖出规则，返回 (平均卖出价, 成交日位置, 是否触发)。

    - ladder(k, step)：T+1 卖第一批，之后每 step 个交易日卖一批，共 k 批（开盘价）
    - ma(w)：某日收盘 < MA(w) → 次日开盘全卖；一直没跌破就拿到期末（按期末收盘市价，triggered=False）
    - trail(pct)：收盘价从起始日后的最高收盘价回撤 pct → 次日开盘全卖；同上兜底
    只卖不买，每条规则最多成交 k 次（ladder）或 1 次（其余），无任何未来数据。
    """
    n = len(closes)
    kind = rule[0]
    if kind == "ladder":
        _, k, step = rule
        days = [t0 + 1 + i * step for i in range(k)]        # 决策在 T 日收盘后做出，最早 T+1 卖
        prices = [opens[d] if d < n else closes[-1] for d in days]  # 数据不够时按期末收盘市价
        return float(np.mean(prices)), min(days[-1], n - 1), True
    if kind == "ma":
        ma = mas[rule[1]]
        for i in range(t0, n):                              # 含起始日当天：起点就已破位也算触发
            if closes[i] < ma[i]:
                j = i + 1
                return (opens[j] if j < n else closes[-1]), min(j, n - 1), True
        return closes[-1], n - 1, False
    if kind == "trail":
        pct = rule[1]
        peak = closes[t0]                                   # 锚：起始日收盘（之后随创新高上移）
        for i in range(t0 + 1, n):
            if closes[i] > peak:
                peak = closes[i]
            elif closes[i] <= peak * (1 - pct):
                j = i + 1
                return (opens[j] if j < n else closes[-1]), min(j, n - 1), True
        return closes[-1], n - 1, False
    raise ValueError(rule)


def scenario_stats(closes, opens, mas, starts):
    """对每个起始日跑全部扰动变体 + 两个对照（当场卖=1.0 / 拿到期末）。
    返回 {rule: DataFrame(相对价, 清仓天数, 触发)}。相对价 = 平均卖出价 / 起始日收盘。"""
    n = len(closes)
    out = {}
    for rule in VARIANTS:
        rel, days, trig = [], [], []
        for t0 in starts:
            price, exec_i, triggered = simulate(rule, t0, closes, opens, mas)
            rel.append(price / closes[t0])
            days.append(exec_i - t0)
            trig.append(triggered)
        out[rule] = pd.DataFrame({"相对价": rel, "清仓天数": days, "触发": trig})
    out[("hold_end",)] = pd.DataFrame({
        "相对价": closes[-1] / closes[starts],
        "清仓天数": n - 1 - np.array(starts), "触发": True})
    return out


def _row(stats, name):
    r = stats["相对价"]
    return (f"{name:<14}{r.median():>7.2f}{r.quantile(0.1):>7.2f}{r.quantile(0.9):>7.2f}"
            f"{r.min():>7.2f}{stats['清仓天数'].mean():>9.0f}天{(1 - stats['触发'].mean()):>9.0%}")


# ---------------------------------------------------------------- 主流程
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    df, info = load_data("00700", start="20100101", force_refresh=True)
    closes, opens = df["close"].to_numpy(), df["open"].to_numpy()
    mas = {w: cal_ma(df["close"], w).to_numpy() for w in (20, 40, 60, 80, 250)}
    n = len(df)

    # ===== A. 当前趋势状态 =====
    px = closes[-1]
    yr = df.iloc[-250:]                                  # 近一年（250 个交易日）
    hi, lo = yr["close"].max(), yr["close"].min()
    hi_d, lo_d = yr["close"].idxmax(), yr["close"].idxmin()
    pos = (px - lo) / (hi - lo)                          # 现价在近一年区间的位置（0=最低 1=最高）
    ma_now = {w: mas[w][-1] for w in (20, 60, 250)}
    seq = [px, ma_now[20], ma_now[60], ma_now[250]]
    align = ("多头排列（价>MA20>MA60>MA250）" if seq == sorted(seq, reverse=True) else
             "空头排列（价<MA20<MA60<MA250）" if seq == sorted(seq) else "缠绕/方向转换中")

    print("=" * 72)
    print(f"腾讯（00700.HK）卖出时机分析　数据截至 {df.index[-1]:%Y-%m-%d}　现价 {px:.1f} 港元（前复权）")
    print("=" * 72)
    print("\n【一、当前趋势状态】")
    for w in (20, 60, 250):
        print(f"  MA{w:<3} = {ma_now[w]:>7.1f}　现价在其{'上' if px >= ma_now[w] else '下'}方 "
              f"{abs(px / ma_now[w] - 1):.1%}")
    print(f"  均线排列：{align}")
    print(f"  近一年区间：{lo:.1f}（{lo_d:%m-%d}）~ {hi:.1f}（{hi_d:%m-%d}），"
          f"现价处于 {pos:.0%} 位置，距近一年高点 {px / hi - 1:+.1%}")

    # ===== B. 历史情景模拟（2010 年以来每个够格的起点都试一遍）=====
    starts = np.array([i for i in range(n) if df.index[i] >= pd.Timestamp("2010-07-01")
                       and n - 1 - i >= FORWARD_MIN])
    stats = scenario_stats(closes, opens, mas, starts)
    print(f"\n【二、历史情景模拟】{len(starts)} 个起始日（{df.index[starts[0]]:%Y-%m-%d} ~ "
          f"{df.index[starts[-1]]:%Y-%m-%d}），每个起点分别执行各规则")
    print("　相对价 = 平均卖出价 ÷ 起始日收盘价（>1 = 比『当场就卖』卖得更好）")
    print(f"  {'规则':<14}{'中位数':>7}{'P10':>7}{'P90':>7}{'最差':>7}{'平均清仓':>9}{'未触发':>9}")
    print(f"  {'立即全卖(基准)':<14}{1.0:>7.2f}{1.0:>7.2f}{1.0:>7.2f}{1.0:>7.2f}{'0天':>9}{'—':>9}")
    for rule in CANON:
        print(" " + _row(stats[rule], RULE_NAMES[rule]))
    print(" " + _row(stats[("hold_end",)], "拿到期末(对照)"))
    print("  ※ 相邻起始日的情景高度重叠（不是独立样本），看的是规则在不同行情起点的稳健性；")
    print("  　未触发=规则一直没等到卖点、按期末收盘市价计入（等价于拿到今天）")

    # 参数扰动：中位数是否形成平台（exit_rules.md 规律6：邻域稳定才可信）
    print("\n【三、参数扰动（过拟合检查：参数挪一挪，结论变不变）】")
    print(f"  {'变体':<18}{'中位数':>7}{'P10':>7}{'最差':>7}{'未触发':>8}")
    for rule in VARIANTS:
        s = stats[rule]
        if rule[0] == "ladder":                      # 分支若写成字典字面量会被全部求值，tuple 长度不一越界
            tag = f"分{rule[1]}批·间隔{rule[2]}日"
        elif rule[0] == "ma":
            tag = f"跌破MA{rule[1]}"
        else:
            tag = f"回撤{rule[1]:.0%}卖"
        print(f"  {tag:<18}{s['相对价'].median():>7.2f}{s['相对价'].quantile(0.1):>7.2f}"
              f"{s['相对价'].min():>7.2f}{(1 - s['触发'].mean()):>8.0%}")

    # ===== C. 关键历史片段复盘 =====
    top_i = int(np.argmax(closes))                       # 历史大顶（2021-02 附近）
    bot_win = closes[top_i:min(top_i + 600, n)]
    bot_i = top_i + int(np.argmin(bot_win))              # 大顶后的恐慌底（2022-10 附近）
    episodes = [("见顶前一月(最乐观时)", max(top_i - 20, 0)), ("历史大顶当天", top_i),
                ("大顶后恐慌底", bot_i), ("近一年起点", n - 1 - 250)]
    print("\n【四、关键历史片段复盘】如果从这些著名时点开始执行（相对价 | 括号=清仓天数）")
    print(f"  {'起点':<18}{'日期':>9}{'分3批':>14}{'MA60':>14}{'回撤15%':>14}{'拿到今天':>8}")
    for label, t0 in episodes:
        cells = []
        for rule in CANON:
            price, exec_i, _ = simulate(rule, t0, closes, opens, mas)
            cells.append(f"{price / closes[t0]:>5.2f}({exec_i - t0:>3d}天)")
        print(f"  {label:<18}{df.index[t0]:%y-%m-%d}{''.join(f'{c:>14}' for c in cells)}"
              f"{closes[-1] / closes[t0]:>8.2f}")

    # ===== D. 今天开始执行，每条规则具体怎么做 =====
    k = 3
    base, rem = divmod(SHARES, k)
    lots = [base + (1 if i < rem else 0) for i in range(k)]
    print(f"\n【五、若今天（{df.index[-1]:%Y-%m-%d}）开始执行，各规则的具体动作】")
    print(f"  分3批：明天卖 {lots[0]} 股，之后每 20 个交易日（≈1 个月）卖 {lots[1]}/{lots[2]} 股，"
          "约 2 个月内清完（零碎股按平台规则处理）")
    if px >= ma_now[60]:
        print(f"  MA60：未触发——现价在 MA60 上方 {px / ma_now[60] - 1:.1%}；"
              f"收盘跌破 {ma_now[60]:.1f} 港元，次日全卖")
    else:
        print(f"  MA60：⭐已触发！现价已在 MA60 下方 {1 - px / ma_now[60]:.1%}，规则=明天全卖")
    print(f"  回撤15%：以现价 {px:.1f} 为初始锚，收盘跌破 {px * 0.85:.1f} 港元次日全卖；"
          "若之后创新高，锚自动上移")
    print(f"  ※ 若该规则从近一年高点 {hi:.1f} 起锚：15% 回撤线 = {hi * 0.85:.1f}，"
          f"半年多前就已离场；『等反弹回 {hi * 0.85:.0f} 再卖』= 要求股价先涨 "
          f"{hi * 0.85 / px - 1:+.0%}，规则不支持这种等待（exit_rules.md：不利因素总是跌完才出现）")

    print("\n【六、必须记住的三句话】")
    print("  1. 量化只能给规则与概率，不能预测股价；任何『精确逃顶』的承诺都不可信")
    print("  2. 一次性卖出决策，分批往往是最稳妥的风险管理（plans/05 重要认知）")
    print("  3. 规则写下来就要机械执行——大多数人亏在『到时候手抖』（exit_rules.md §4）")
    print("  ※ 卖出成本（佣金/平台费）未计入——一次性卖出金额固定、影响很小；"
          "税费/外汇/卖出窗口请自行向券商或公司确认")

    # ===== 图：近一年 K 线 + 均线 + 关键位 =====
    win = df.iloc[-250:].copy()
    for w, c in [(20, "orange"), (60, "blue"), (250, "purple")]:
        win[f"MA{w}"] = mas[w][-250:]
    aps = [mpf.make_addplot(win[f"MA{w}"], color=c, width=1.0)
           for w, c in [(20, "orange"), (60, "blue"), (250, "purple")]]
    mc = mpf.make_marketcolors(up="red", down="green", edge="inherit",
                               wick="inherit", volume="inherit")     # 红涨绿跌，中国配色
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle="-.", gridcolor="0.85",
                               rc={"font.family": ["SimHei", "Microsoft YaHei"],
                                   "axes.unicode_minus": False})     # mplfinance 样式独立，中文字体要塞进 rc
    fig, axes = mpf.plot(win, type="candle", style=style, addplot=aps, volume=True,
                         returnfig=True, figsize=(13, 8),
                         title=f"\n腾讯 00700.HK 近一年　现价 {px:.1f}　{align}")
    ax = axes[0]
    x_last = len(win) - 1                                # mplfinance 内部 x 轴就是整数位置 0..N-1
    ax.axhline(hi, color="red", ls="--", lw=1, alpha=0.7)
    ax.axhline(lo, color="green", ls="--", lw=1, alpha=0.7)
    ax.axhline(px, color="0.3", ls=":", lw=1)
    ax.text(x_last, hi, f"近一年高 {hi:.1f}（{hi_d:%m-%d}）", color="red",
            fontsize=9, ha="right", va="bottom")
    ax.text(x_last, lo, f"近一年低 {lo:.1f}（{lo_d:%m-%d}）", color="green",
            fontsize=9, ha="right", va="top")
    ax.text(0, px, f"现价 {px:.1f} ", color="0.3", fontsize=9, ha="left", va="top")
    ax.legend(handles=[Line2D([], [], color=c, lw=1.2, label=f"MA{w}")
                       for w, c in [(20, "orange"), (60, "blue"), (250, "purple")]],
              loc="lower left", fontsize=8)
    out = DATA_DIR / "tencent_exit_00700.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\n📊 K 线图已保存：{out}")


if __name__ == "__main__":
    main()
