# -*- coding: utf-8 -*-
"""
analysis/analyze_grid_etf.py — 计划 16 增补：知乎"波动ETF"网格策略回测

策略原文（Knowledge/zhihu/波动ETF策略.md）规则翻译（口述 → 机械化，歧义处标注）：
1. 标的：波动大的指数（作者建议科创板/创业板）→ 用科创50(000688)、创业板指(399006)
   【用指数点位而非 ETF 价：百分比网格对两者等价，指数无拆分/分红/跟踪误差问题；
    实盘买对应 ETF 会有 ~0.5%/年的管理费+跟踪误差，披露】
2. 开仓闸门：收盘价 ≤ 70% × 滚动 3 年最高收盘 → 网格 T+1 启动，锚点=T 收盘，
   "前高"=启动时的滚动 3 年最高（作者原话"破了前高就全清"里的前高）
   【作者自述 2023-04 在 1.3 启动（=前高 1.7 的 76%），违反他自己 70% 的规则——
    口述与规则有出入，本回测按规则 70% 机械化执行】
3. 三档网格（等比阶梯，共用锚点）：价格向下穿越档→买、向上穿越档→卖（同一梯子）
   档1 间距 8%：买 8 份 / 卖 6 份；档2 间距 15%：买 15 份 / 卖 12 份；
   档3 间距 30%：买 30 份 / 卖 20 份。买>卖的不对称 = 震荡中净吸筹（作者"持仓不死"）
4. 资金：10000 元 = 200 份 × 50 元；现金账户自然封顶（没钱就买不了）= "200 份"上限
5. 清仓：当日最高价 ≥ 前高 → 以前高价全清（条件单触及成交），回到待命等下次闸门
6. 作者提到"有了闲钱就转进去"（类定投）→ 本回测固定 10000 元不追加，披露

成交模型（条件单语义，无未来函数的关键）：
- 网格限价单是【提前挂好】的：当日 low ≤ 买档价 → 以档价成交；high ≥ 卖档价 → 以档价
  成交。不用任何未来数据（挂单在开盘前就存在）
- 同日双边触及：按路径假设处理——收阳按 open→low→high→close（先买后卖），
  收阴反之（先卖后买），披露
- 触发判定在 T 收盘 → 网格 T+1 才生效（不用当天数据赚当天的钱）

成本两口径：免5（万 1）vs 不免5（最低 5 元/笔）——10000 元拆 200 份，
单笔 300~1500 元，不免5 时最低佣金占 0.3~1.7%，是这个小额策略的生死线。
空仓现金两口径：0%（项目保守惯例）vs 余额宝 0.9%（用户 2026-07 提供的数字）。

运行：python analysis/analyze_grid_etf.py
产出：终端报告 + data/grid_etf_000688.png / grid_etf_399006.png

⚠ 为什么这个脚本自写事件循环、没走 quant/ 框架（CLAUDE.md 规则 6/7 要求说明）：
   网格是**盘中触价成交**——限价单提前挂好，当日 low/high 碰到档价就以【档价】成交，
   一天可能成交多档。而框架两个引擎都只做"T 日决策 → T+1 收盘/净值成交"
   （engine.py 还只有满仓/空仓两态），表达不了"当天在某个价位成交、且分档部分仓位"。
   属于 Knowledge/strategy_translation.md 文末"落不进框架的三类"第 1 类。
   已复用的框架件：quant.data.load_data 取数、quant.metrics 绩效、
   report_portfolio_parts.perf_row 绩效表——只有成交循环是本地的。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fetch_data import DATA_DIR
from quant import metrics
from quant.data import load_data
from quant.report_portfolio_parts import perf_row

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

INITIAL = 10000.0
PORTION = INITIAL / 200          # 1 份 = 50 元
TIERS = [(0.08, 8, 6), (0.15, 15, 12), (0.30, 30, 20)]  # (间距, 买份, 卖份)
CEILING = 0.70                    # 开仓闸门：收盘 ≤ 70% × 滚动3年最高
HIGH_WIN = 756                    # 3 年 ≈ 756 个交易日


def run_grid(df, tiers=TIERS, ceiling=CEILING, cost_rate=0.0001,
             min_fee=0.0, idle_apy=0.0):
    """网格回测主函数。返回 (equity, trades_log, 状态摘要)。

    df: date 索引 + open/high/low/close。从首个"3年高点"可用日起跑。
    cost_rate: 佣金率（万 1 = 0.0001）；min_fee: 单笔最低佣金（免5=0，不免5=5）
    idle_apy: 闲置现金年化利率（0 或 0.009）
    """
    df = df.copy()
    # 滚动 3 年最高收盘价（只用当日及以前数据；不足 1 年时不出信号，防"新标的假高点"）
    df["roll_high"] = df["close"].rolling(HIGH_WIN, min_periods=250).max()

    cash, shares = INITIAL, 0.0
    active = False          # 网格是否运行中
    anchor = anchor_high = None
    cur_k = {t[0]: 0 for t in tiers}   # 各档当前所处阶梯（0=锚点，下跌 k 增大）
    equity, log = [], []
    total_fee = 0.0

    def fee(amount):
        return max(amount * cost_rate, min_fee) if amount > 0 else 0.0

    dates = df.index
    started = False
    for i in range(len(df)):
        d = dates[i]
        o, h, l, c = (df.iloc[i][k] for k in ("open", "high", "low", "close"))
        rh = df.iloc[i]["roll_high"]

        if not active:
            # —— 待命：T 收盘判定闸门（rh 含 T，无未来函数），T+1 启动 ——
            if started and pd.notna(rh) and c <= ceiling * rh:
                active, anchor, anchor_high = True, c, rh
                cur_k = {t[0]: 0 for t in tiers}
                log.append({"日期": d, "动作": "启动网格", "价格": c,
                            "金额": 0, "备注": f"锚点 {c:.2f}，前高 {rh:.2f}"})
            started = True
        else:
            # —— 网格运行中（本日已是启动次日之后）——
            # ① 破前高 → 全清（条件单盘中触及成交，优先处理）
            if shares > 0 and h >= anchor_high:
                fill = max(anchor_high, o)  # 高开越过前高时按开盘价（拿不到更好的）
                f = fee(shares * fill)
                cash += shares * fill - f
                total_fee += f
                log.append({"日期": d, "动作": "破前高全清", "价格": fill,
                            "金额": shares * fill, "备注": f"前高 {anchor_high:.2f}"})
                shares, active = 0.0, False
                anchor = anchor_high = None
            else:
                # ② 正常网格：先按路径假设排买卖顺序
                bull = c >= o
                seq = [("buy", l), ("sell", h)] if bull else [("sell", h), ("buy", l)]
                for side, extreme in seq:
                    for step, buy_p, sell_p in tiers:
                        r = 1 - step
                        if side == "buy":
                            # 当日最低价触及的最深档（floor 语义，见文件头推导）
                            k_t = int(np.floor(np.log(extreme / anchor) / np.log(r)))
                            while cur_k[step] < k_t:
                                cur_k[step] += 1
                                px = anchor * r ** cur_k[step]
                                amt = buy_p * PORTION
                                if px <= 0 or cash < amt + fee(amt):
                                    break  # 现金耗尽 = "200 份用完"（自然封顶）
                                f = fee(amt)
                                shares += amt / px
                                cash -= amt + f
                                total_fee += f
                                log.append({"日期": d, "动作": f"买[{step:.0%}档]",
                                            "价格": px, "金额": amt,
                                            "备注": f"第{cur_k[step]}档"})
                        else:
                            k_t = int(np.ceil(np.log(extreme / anchor) / np.log(r)))
                            while cur_k[step] > k_t:
                                px = anchor * r ** (cur_k[step] - 1)
                                amt = sell_p * PORTION
                                qty = min(amt / px, shares)
                                if qty <= 0:
                                    cur_k[step] = k_t
                                    break
                                f = fee(qty * px)
                                cash += qty * px - f
                                total_fee += f
                                shares -= qty
                                cur_k[step] -= 1
                                log.append({"日期": d, "动作": f"卖[{step:.0%}档]",
                                            "价格": px, "金额": qty * px,
                                            "备注": f"回到第{cur_k[step]}档"})
                # 日终档位跟随收盘价（防次日重复成交同一档）
                for step, _, _ in tiers:
                    r = 1 - step
                    if c < anchor:
                        cur_k[step] = max(cur_k[step],
                                          int(np.floor(np.log(c / anchor) / np.log(r))))
                    else:
                        cur_k[step] = min(cur_k[step],
                                          int(np.ceil(np.log(c / anchor) / np.log(r))))
        # —— 记账（现金按日计息，0 或余额宝口径）——
        cash *= (1 + idle_apy / 365)
        equity.append(cash + shares * c)

    eq = pd.Series(equity, index=dates)
    eq.attrs["总费用"] = total_fee
    summary = {"期末持仓市值": shares * df["close"].iloc[-1],
               "期末状态": "网格运行中" if active else "待命（空仓）"}
    return eq, pd.DataFrame(log), summary


def report(name, df, eq, log, summary, label):
    print(f"\n{'=' * 74}\n{name}（{label}）")
    b = df["close"].reindex(eq.index)
    # 绩效行统一用框架的 perf_row（口径单一来源，见 Knowledge/metrics.md）
    rows = [perf_row(eq, "网格策略", INITIAL),
            perf_row(b / b.iloc[0] * INITIAL, "买入持有(对照)", INITIAL)]
    print(f"区间：{eq.index[0]:%Y-%m-%d} ~ {eq.index[-1]:%Y-%m-%d}"
          f"（{(eq.index[-1] - eq.index[0]).days / 365.25:.1f} 年）  初始 {INITIAL:.0f} 元")
    print(pd.DataFrame(rows).set_index("口径").to_string())
    n_buy = int(log["动作"].str.startswith("买").sum()) if len(log) else 0
    n_sell = int(log["动作"].str.startswith("卖").sum()) if len(log) else 0
    print(f"成交：买 {n_buy} 次 / 卖 {n_sell} 次，总费用 {eq.attrs['总费用']:.1f} 元；"
          f"期末状态：{summary['期末状态']}，期末持仓市值 {summary['期末持仓市值']:.0f} 元")
    if len(log):
        print("关键节点：")
        key = log[log["动作"].isin(["启动网格", "破前高全清"])]
        for _, r_ in key.iterrows():
            print(f"  {r_['日期']:%Y-%m-%d}  {r_['动作']}  @ {r_['价格']:.2f}  {r_['备注']}")
    return eq


def plot(name, df, eq, log, path):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 2]})
    b = df["close"].reindex(eq.index)
    ax1.plot(b.index, b, color="0.25", lw=1, label="指数收盘")
    buys = log[log["动作"].str.startswith("买")]
    sells = log[log["动作"].str.startswith("卖")]
    ax1.scatter(buys["日期"], buys["价格"], marker="^", color="red", s=22,
                zorder=5, label=f"买入 {len(buys)} 次")
    ax1.scatter(sells["日期"], sells["价格"], marker="v", color="green", s=22,
                zorder=5, label=f"卖出 {len(sells)} 次")
    ax1.set_title(f"{name} 网格买卖点（红▲买/绿▼卖）")
    ax1.legend()
    ax1.grid(alpha=0.3)
    ax2.plot(eq.index, eq / eq.iloc[0], color="red", lw=1.8, label="网格策略净值")
    ax2.plot(b.index, b / b.iloc[0], color="0.5", lw=1.2, label="买入持有")
    ax2.set_title("净值对比（归一化）")
    ax2.legend()
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    print(f"✓ 图已存 {path}")


def run_one(query, name):
    df, _ = load_data(query, start="20200101")
    print(f"\n########## {name} ##########")
    # 主口径：免5（万1）+ 空仓现金 0.9%（余额宝）
    eq, log, summary = run_grid(df, min_fee=0.0, idle_apy=0.009)
    report(name, df, eq, log, summary, "免5万1 + 现金计余额宝0.9%")
    plot(name, df, eq, log, DATA_DIR / f"grid_etf_{query}.png")
    # 敏感性①：不免5（最低 5 元/笔）——小额网格的生死线
    eq2, log2, s2 = run_grid(df, min_fee=5.0, idle_apy=0.009)
    print(f"\n--- 成本敏感性（不免5，最低5元/笔）---")
    print(f"期末 {eq2.iloc[-1]:.0f} 元（vs 免5 的 {eq.iloc[-1]:.0f} 元），"
          f"总费用 {eq2.attrs['总费用']:.0f} 元（vs {eq.attrs['总费用']:.0f} 元）——"
          f"差额 {eq.iloc[-1] - eq2.iloc[-1]:.0f} 元全交给了券商")
    # 敏感性②：闸门 70% → 65% / 75% / 80%（防过拟合：结论不能只在 70% 成立）
    print(f"\n--- 闸门敏感性（其他参数不动）---")
    rows = []
    for cg in (0.65, 0.70, 0.75, 0.80):
        e_, l_, _ = run_grid(df, ceiling=cg, min_fee=0.0, idle_apy=0.009)
        rows.append({"闸门": f"{cg:.0%}", "期末": round(e_.iloc[-1]),
                     "年化": f"{metrics.annual_return(e_):+.2%}",
                     "最大回撤": f"{metrics.max_drawdown(e_):.1%}",
                     "成交次数": len(l_)})
    print(pd.DataFrame(rows).set_index("闸门").to_string())


if __name__ == "__main__":
    run_one("000688", "科创50")
    run_one("399006", "创业板指")
