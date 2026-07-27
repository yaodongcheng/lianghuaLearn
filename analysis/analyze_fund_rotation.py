# -*- coding: utf-8 -*-
"""analysis/analyze_fund_rotation.py — 计划04：场外基金动量轮动回测（可重跑）

主战场的第一仗：沪深300联接A(110020) / 中证500联接A(160119) 动量轮动，
对比"一直持有沪深300联接"。策略依据见 Knowledge/funds.md §五.2。

⭐ 本脚本的实验矩阵（先写死再看结果，防后视镜）：
                月度调仓          每日检查
  A 类费率      计划原始规格       费用死刑演示
  C 类费率      ——               候选实盘版（≥7 天才换仓，免申赎费）
  零费用        ——               上限参照（经典二八轮动长什么样）
结论预览（详见 plans/04）：轮动的命门是"检查频率"和"费用结构"，不是动量本身。

规则（三个版本共用）：
- 比较两基金近 20 个交易日累计净值涨幅，持有高者；两者都跌 → 赎回成现金
- T 日收盘出信号 → T+1 按当晚净值成交（funds.md §三.2：信号用今日收盘，
  就只能按下一交易日净值——这不是未来函数，是场外基金的真实约束）
- 每日检查版：每月第一个交易日 ⇒ 改为每个交易日收盘都评估

基金费用口径（funds.md §二.4，plan04 验收标准）：
- A 类：申购 0.15%（支付宝 1 折）+ 赎回阶梯（<7天 1.5% / 7天~1年 0.5% / 1~2年 0.25% / ≥2年 0）
- C 类：申购 0 + 赎回 ≥7天 0（<7天仍 1.5%），但净值外日计提 0.25%/年服务费（按日扣模拟）
  + 约束：持仓不足 7 个自然日不许换仓（信号顺延到明天再评估）——纪律性避开惩罚费
- 现金期收益按 0 计（保守；实际放货基约 1.5%~2%/年）

数据口径（实测坑，plans/04 笔记）：用累计净值 acc_nav 的日涨幅；**不要用接口的 daily_ret**——
它在除息日把分红当亏损（实测 160119 于 2026-07-24 除息：daily_ret -2.47% vs 累计净值 -2.36%）。
产出：终端报告 + data/fund_rotation.png（净值曲线 + 回撤 + 现金期灰底）
"""
import sys
from pathlib import Path

# 脚本位于 analysis/ 子目录：Python 只把【脚本所在目录】加进 import 路径，
# 不会加项目根目录——手动补上，否则 from quant... / fetch_data 全部找不到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")                      # 只存 PNG 不弹窗（项目统一约定）
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from fetch_data import DATA_DIR, check_daily, fetch_fund_nav
from quant import metrics

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

FUNDS = {"300": ("110020", "易方达沪深300ETF联接A"),
         "500": ("160119", "南方中证500ETF联接(LOF)A")}
MOM = 20                                   # 动量窗口（平庸整数；扰动 15/25）
SUB_FEE = 0.0015                           # A 类申购费（支付宝 1 折）
C_SERVICE = 0.0025                         # C 类销售服务费/年（日计提模拟用）


def redeem_fee_a(days_held):
    """A 类赎回费阶梯（自然日）。funds.md §二.4。"""
    if days_held < 7:
        return 0.015
    if days_held < 365:
        return 0.005
    if days_held < 730:
        return 0.0025
    return 0.0


def load_fund(code, label):
    """基金净值 → date 索引的累计净值 Series（见文件头数据口径说明）。"""
    raw = fetch_fund_nav(code)
    df = pd.DataFrame({"date": raw["date"],
                       "close": raw["acc_nav"].fillna(raw["nav"])})
    # check_daily 内部用位置取值（df['close'][idx-1]），必须在整数索引的表上调用
    check_daily(df.assign(open=df["close"], high=df["close"], low=df["close"], volume=0),
                f"{label}（累计净值模式）")
    return df.set_index(pd.to_datetime(df["date"])).sort_index()["close"]


def simulate(ret_a, ret_b, mom=MOM, freq="M", fee_model="A", min_hold=0, gap=0):
    """轮动主模拟。输入两基金日收益 Series（已对齐日期），返回
    (净值 Series, 持仓 Series, 换仓记录 list[(日期, 从, 到, 费率, 持有天数)])。

    每日顺序：①按当前持仓计当日收益（C 类口径先扣日服务费）
    → ②若昨日有换仓指令，今日按净值成交并扣费（T+1 的收益属于旧仓，真实约束）
    → ③今日是检查日则收盘后出信号；不足 min_hold 自然日则顺延（明天再评估）。
    gap>0 时买入侧模拟"赎回到账空窗"（funds.md §二.3：赎回到账 T+1~T+7）：
    卖出成交后资金在途 gap 天（收益 0、锁定不接受新信号），到账日收盘才买入。
    """
    dates = ret_a.index
    ra, rb = ret_a.to_numpy(), ret_b.to_numpy()
    acc_a = (1 + ret_a).cumprod()            # 动量用净值算
    acc_b = (1 + ret_b).cumprod()
    month_starts = set(pd.Series(dates, index=dates).groupby(
        [dates.year, dates.month]).first())  # set(Series) 取的是值：每月首个交易日

    holding, pending, leg_start = "cash", None, None
    limbo, limbo_target = 0, None            # 在途资金：剩余天数 / 目的地
    eq, hold_s, switches = [1.0], [], []
    c_drag = (1 + C_SERVICE) ** (1 / 252) - 1 if fee_model == "C" else 0.0

    for i in range(1, len(dates)):
        d = dates[i]
        if limbo > 0:                        # 在途：收益 0，锁定；到账日收盘买入
            r, limbo = 0.0, limbo - 1
            if limbo == 0:
                holding, leg_start = limbo_target, d
        else:
            r = {"300": ra[i], "500": rb[i]}.get(holding, 0.0)
            if holding != "cash":
                r = (1 + r) * (1 - c_drag) - 1
            if pending is not None:          # T+1 按当晚净值成交（新旧仓同价换）
                days_held = (d - leg_start).days if leg_start is not None else 999
                if fee_model == "free":
                    fee = 0.0
                elif fee_model == "C":
                    fee = 0.015 if (holding != "cash" and days_held < 7) else 0.0
                else:                        # A 类：赎回阶梯 + 申购 0.15%
                    fee = (redeem_fee_a(days_held) if holding != "cash" else 0.0) + \
                          (SUB_FEE if pending != "cash" else 0.0)
                r = (1 + r) * (1 - fee) - 1
                switches.append((d, holding, pending, fee, days_held))
                if gap > 0 and pending != "cash":      # 买入侧进入在途空窗
                    limbo, limbo_target, holding = gap, pending, "cash"
                else:
                    holding, leg_start = pending, d
                pending = None
            # ⭐ 信号前提：资金不在途（limbo==0）。否则刚卖完进在途的当天 holding 已被
            # 置成 cash，会被误判成"空仓可买"而再挂指令 → 陈旧指令跨在途期残留，反复吃惩罚费
            if limbo == 0:
                is_check = (d in month_starts) if freq == "M" else True
                if is_check and i >= mom:    # 收盘后出信号（只用今日及之前数据）
                    ma = acc_a.iloc[i] / acc_a.iloc[i - mom] - 1
                    mb = acc_b.iloc[i] / acc_b.iloc[i - mom] - 1
                    target = "cash" if max(ma, mb) < 0 else ("300" if ma >= mb else "500")
                    days_in_leg = (d - leg_start).days if leg_start is not None else 999
                    if target != holding and (holding == "cash" or days_in_leg >= min_hold):
                        pending = target     # 锁定期内不挂指令，明天收盘重新评估
        eq.append(eq[-1] * (1 + r))
        hold_s.append(holding)
    eq = pd.Series(eq, index=dates)
    hold_s = pd.Series(hold_s, index=dates[1:]).reindex(dates, method="ffill")
    return eq / eq.iloc[0], hold_s, switches


def brief(name, eq):
    return (f"{name:<24}{eq.iloc[-1] / eq.iloc[0] - 1:>+9.1%}{metrics.annual_return(eq):>+8.1%}"
            f"{metrics.max_drawdown(eq):>9.1%}{metrics.sharpe_ratio(eq):>7.2f}"
            f"{metrics.calmar_ratio(eq):>8.2f}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    nav = {k: load_fund(code, label) for k, (code, label) in FUNDS.items()}
    both = pd.concat(nav, axis=1, keys=["300", "500"]).dropna()   # 日期取交集（都是境内交易日）
    ret = both.pct_change().fillna(0.0)
    print(f"✓ 对齐后 {len(both)} 个交易日：{both.index[0]:%Y-%m-%d} ~ {both.index[-1]:%Y-%m-%d}")

    warm = ret.iloc[MOM:]                    # 留出 20 日动量预热段
    runs = {                                 # 实验矩阵：名称 → (freq, fee_model, min_hold, gap)
        "月度·A类(原始规格)": ("M", "A", 0, 0),
        "每日·A类(费用死刑)": ("D", "A", 0, 0),
        "每日·C类≥7天": ("D", "C", 7, 0),
        "每日·C类+3天空窗(实盘)": ("D", "C", 7, 3),
        "每日·零费用(上限)": ("D", "free", 0, 0),
    }
    results = {name: simulate(warm["300"], warm["500"], freq=f, fee_model=fee,
                              min_hold=mh, gap=g)
               for name, (f, fee, mh, g) in runs.items()}
    bench = {k: (1 + warm[k]).cumprod() * (1 - SUB_FEE) for k in ("300", "500")}
    bench = {k: s / s.iloc[0] for k, s in bench.items()}   # 基准期初扣一次申购费，买定离手

    CAND = "每日·C类+3天空窗(实盘)"           # 主结论用最贴近支付宝实操的口径
    eq0 = results[CAND][0]
    years = (eq0.index[-1] - eq0.index[0]).days / 365.25
    print(f"\n【一、实验矩阵 vs 基准】{eq0.index[0]:%Y-%m-%d} ~ {eq0.index[-1]:%Y-%m-%d}（{years:.1f} 年）")
    print(f"  {'':26}{'总收益':>9}{'年化':>8}{'最大回撤':>9}{'夏普':>7}{'卡玛':>8}")
    for name, (eq, _, _) in results.items():
        print(" " + brief(name, eq))
    print(" " + brief("一直持有300联接", bench["300"]))
    print(" " + brief("一直持有500联接", bench["500"]))
    print("  ※ 现金期收益按 0 计（实际放货基约 +1.5%~2%/年，策略只会更好）；"
          "空窗=赎回到账在途 3 天（funds.md §二.3）")

    print(f"\n【二、调仓统计（验收项：年均调仓是否费用可承受）】")
    for name in ("月度·A类(原始规格)", "每日·A类(费用死刑)", CAND):
        eq, _, sw = results[name]
        fee_sum = sum(t[3] for t in sw)
        under7 = sum(1 for t in sw if t[1] != "cash" and t[4] < 7)   # 基金腿<7天才吃惩罚费
        buys = sum(1 for t in sw if t[2] != "cash")
        print(f"  {name}：换仓 {len(sw)} 次（年均 {len(sw) / years:.1f}，"
              f"其中买入 {buys} 次），费用合计 ≈{fee_sum:.0%}，<7 天基金腿 {under7} 条")
    print("  ※ 买入空窗 3 天是真实摩擦；实操可选【同一家基金公司】的 C 类对用『基金转换』消除"
          "（本回测的两基金分属易方达/南方，无法互转，故保守计入）")

    print(f"\n【三、参数扰动·实盘版（动量窗口 15/20/25，防过拟合）】")
    print(f"  {'窗口':<8}{'年化':>8}{'最大回撤':>9}{'夏普':>7}{'换仓次数':>8}")
    for m in (15, 20, 25):
        w = ret.iloc[m:]
        e, _, sw = simulate(w["300"], w["500"], mom=m, freq="D", fee_model="C",
                            min_hold=7, gap=3)
        print(f"  {m:<8}{metrics.annual_return(e):>+8.1%}{metrics.max_drawdown(e):>9.1%}"
              f"{metrics.sharpe_ratio(e):>7.2f}{len(sw):>8}")

    print(f"\n【四、分时代检验（实盘版，看是否靠某个时代吃饭）】")
    for label, sl in [("2009~2016", slice(None, "2016-12-31")),
                      ("2017至今", slice("2017-01-01", None))]:
        print(f"  ── {label} ──")
        for name, e in [("每日·C类实盘", eq0), ("持有300", bench["300"]), ("持有500", bench["500"])]:
            sub = e.loc[sl]
            print(f"    {name:<12}{metrics.annual_return(sub):>+8.1%} 年化"
                  f"{metrics.max_drawdown(sub):>9.1%} 回撤{metrics.sharpe_ratio(sub):>7.2f} 夏普")

    # ===== 图：实盘版 vs 月度A类 vs 双基准 + 现金期灰底 + 实盘版回撤 =====
    hold_c = results[CAND][1]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
    for d in hold_c[hold_c == "cash"].index:  # 现金期灰底：一眼看出策略什么时候躲在场外
        ax1.axvspan(d, d, color="0.5", alpha=0.12, lw=0)
    ax1.plot(eq0.index, eq0, color="red", lw=1.5, label="每日检查·C类+3天空窗（实盘版）")
    ax1.plot(results["月度·A类(原始规格)"][0].index, results["月度·A类(原始规格)"][0],
             color="darkorange", lw=1.0, ls="--", label="月度·A类（计划原始规格）")
    ax1.plot(bench["300"].index, bench["300"], color="0.5", lw=1.1, label="一直持有300联接")
    ax1.plot(bench["500"].index, bench["500"], color="steelblue", lw=1.1, label="一直持有500联接")
    ax1.set_title(f"沪深300/中证500 动量轮动（{MOM}日动量）vs 一直持有　实盘版年化 "
                  f"{metrics.annual_return(eq0):+.1%} vs 持有300 {metrics.annual_return(bench['300']):+.1%}　"
                  f"回撤 {metrics.max_drawdown(eq0):+.1%} vs {metrics.max_drawdown(bench['300']):+.1%}")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.25)
    ax1.text(0.99, 0.03, "灰底 = 实盘版持有现金（两基金 20 日涨幅均 < 0）",
             transform=ax1.transAxes, ha="right", fontsize=8, color="0.4")

    dd = eq0 / eq0.cummax() - 1
    ax2.fill_between(dd.index, dd, 0, color="red", alpha=0.3, label="实盘版回撤")
    dd3 = bench["300"] / bench["300"].cummax() - 1
    ax2.plot(dd3.index, dd3, color="0.5", lw=0.9, label="持有300回撤")
    ax2.legend(loc="lower left", fontsize=8)
    ax2.grid(alpha=0.25)
    out = DATA_DIR / "fund_rotation.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"\n📊 净值对比图已保存：{out}")


if __name__ == "__main__":
    main()
