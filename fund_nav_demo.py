# -*- coding: utf-8 -*-
"""
fund_nav_demo.py — 场外基金净值拉取与基准对比演示（计划 04 第一步）

标的：永赢先锋半导体智选混合发起C（025209）——用户持仓关注的基金
内容：拉净值 → 与沪深300 归一化对比 → 打印关键风险指标
教学点：基金的"一天一个价"决定了它天然适合做日频低频策略；
       但行业主题基金波动巨大，先看懂风险再谈策略。
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from fetch_data import fetch_daily, fetch_fund_nav

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False  # 负号正常显示（净值增长率有负值）

CODE = "025209"

# ============================================================
# 1. 拉基金净值（自动缓存）+ 沪深300 作基准（从成立日起对齐）
# ============================================================
fund = fetch_fund_nav(CODE)
start = fund["date"].iloc[0].strftime("%Y%m%d")
idx = fetch_daily("idx", "000300", start=start)

# 归一化：两条曲线都从 1 起步（基准对比的标准做法，见 data_sources.md 五）
m = idx[["date", "close"]].merge(fund[["date", "nav"]], on="date", how="inner")
m["fund"] = m["nav"] / m["nav"].iloc[0]
m["bench"] = m["close"] / m["close"].iloc[0]

fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(m["date"], m["fund"], label=f"永赢半导体C（{CODE}）", linewidth=1.5)
ax.plot(m["date"], m["bench"], label="沪深300（同期）", linewidth=1.2, alpha=0.8)
ax.axhline(1, color="gray", linewidth=0.8, linestyle="--")
ax.legend()
ax.grid(linestyle="-.", alpha=0.5)
ax.set_title(f"基金 vs 基准（{m['date'].iloc[0]:%Y-%m-%d} 起归一化）")
out = f"data/fund_{CODE}_vs_hs300.png"
fig.savefig(out, dpi=120, bbox_inches="tight")
print(f"已保存：{out}")

# ============================================================
# 2. 关键指标速览（正式绩效模块是计划 03，这里先粗看）
# ============================================================
ret_fund = m["fund"].iloc[-1] - 1
ret_bench = m["bench"].iloc[-1] - 1
cummax = m["fund"].cummax()
mdd = (m["fund"] / cummax - 1).min()          # 最大回撤：从最高点跌最深多少
vol_ann = fund["daily_ret"].std() * (252 ** 0.5)  # 日增长率标准差 ×√252 ≈ 年化波动率

print(f"\n区间：{m['date'].iloc[0]:%Y-%m-%d} ~ {m['date'].iloc[-1]:%Y-%m-%d}（{len(m)} 个交易日）")
print(f"基金累计收益：{ret_fund:+.1%}    同期沪深300：{ret_bench:+.1%}")
print(f"基金最大回撤：{mdd:.1%}    年化波动率：约 {vol_ann:.0f}%（股票基金 20% 就算不低）")
print("\n单日涨跌 Top3（感受行业主题基金的刺激程度）：")
top = fund.reindex(fund["daily_ret"].abs().nlargest(3).index)
for _, r in top.iterrows():
    print(f"  {r['date']:%Y-%m-%d}  {r['daily_ret']:+.2f}%    净值 {r['nav']:.4f}")
print("\n最近 5 天：")
print(fund.tail(5).to_string(index=False))
