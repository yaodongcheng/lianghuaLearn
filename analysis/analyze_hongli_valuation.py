# -*- coding: utf-8 -*-
"""中证红利估值体检（每月 5 号检查时可复跑，约 10 秒）

回答的问题：**红利这条腿现在"贵不贵"，该不该因为点位高而停买？**

判断原则（教学点）：
- 看"贵不贵"不能只看点位分位。红利指数买的是分红，核心估值尺子是【股息率】：
  点位高 × 股息率也高 = 这轮上涨是利润/分红撑起来的（良性），不是估值泡沫。
- 注意：中证官网的估值接口**只回传近 20 个交易日**（没有长历史分位可算），
  所以这里用**经验阈值**判断贵贱（20 年经验中枢：股息率 4%~5.5%，
  2015 泡沫顶曾跌破 3%）：
    股息率 ≥ 4.5% → 正常偏高，继续按计划买
    3.5% ~ 4.5% → 中性
    < 3.5%     → 偏贵，回 plans/24 讨论是否减速
- 想拉长历史分位的替代源：乐咕乐股只覆盖少数指数（有深证红利/上证红利，
  没有中证红利），可作同类参照（2026-08-05 实测：深证红利 PE 19.9 vs 2015 顶 28.5；
  上证红利 PE 8.5 vs 2015 顶 10.7——都远低于泡沫顶）。

数据源（都走 fetch_data.py 轮子）：
- 腾讯源指数日线（fetch_daily 双源对部分中证指数回传旧数据，见轮子 docstring）
- 中证指数官网估值（市盈率1/2、股息率1/2，近 20 个交易日）

产出：文字摘要 + data/hongli_valuation_YYYYMMDD.png（点位/股息率双图）。
"""
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")                       # 无界面后端：只存 PNG 不弹窗
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetch_data import DATA_DIR, fetch_index_daily_tx, fetch_index_value_csindex

plt.rcParams["font.family"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False  # 负号用 ASCII，防字体缺方块


def main():
    # ---------- 1) 点位（2005~今）----------
    df = fetch_index_daily_tx("000922")
    c = df["close"]
    cur, cur_date = c.iloc[-1], str(df["date"].iloc[-1])[:10]
    hi, hi_date = c.max(), str(df.loc[c.idxmax(), "date"])[:10]
    pos_pct = (c < cur).mean() * 100         # 当前点位高于历史上多少比例的交易日
    y1 = df.tail(250)["close"]
    y1_chg = (cur / y1.iloc[0] - 1) * 100

    # ---------- 2) 估值（中证官网：市盈率1/股息率2 动态口径，仅近 20 交易日）----------
    v = fetch_index_value_csindex("000922")
    dy = pd.to_numeric(v["股息率2"].replace("-", None), errors="coerce").dropna()
    pe = pd.to_numeric(v["市盈率1"].replace("-", None), errors="coerce").dropna()
    cur_dy = dy.iloc[-1]
    cur_pe = pe.iloc[-1]

    print("===== 中证红利 估值体检 =====")
    print(f"指数点位（{cur_date}）：{cur:.1f} | 全历史最高 {hi:.1f}（{hi_date}），"
          f"距最高 {(cur/hi-1)*100:+.1f}% | 历史分位 {pos_pct:.0f}%（高！）")
    print(f"近一年涨跌：{y1_chg:+.1f}%")
    print(f"股息率2（近12个月分红口径，{v['日期'].iloc[-1].date()}）：{cur_dy:.2f}% "
          f"（经验中枢 4%~5.5%，2015 泡沫顶曾跌破 3%）")
    print(f"市盈率1（静态）：{cur_pe:.2f}（同类参照：上证红利 8.5 vs 2015 顶 10.7，"
          f"深证红利 19.9 vs 28.5）")
    if cur_dy >= 4.5:
        print("→ 结论：点位虽高，但股息率仍在正常偏高区间 → 估值不贵，按计划继续买。")
    elif cur_dy >= 3.5:
        print("→ 提示：股息率中性区间，保持观察；每月检查时复跑本脚本。")
    else:
        print("→ 警告：股息率跌破 3.5%，红利估值偏贵，回 plans/24 讨论是否减速。")

    # ---------- 3) 图：上点位、下股息率 ----------
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 7), sharex=False,
        gridspec_kw={"height_ratios": [1.15, 1]})
    fig.suptitle("中证红利：点位 vs 股息率（同一时刻，两个世界）", fontsize=13)

    ax1.plot(pd.to_datetime(df["date"]), c, lw=0.8, color="#b03030", label="指数点位")
    ax1.axhline(hi, color="gray", ls="--", lw=1)
    ax1.text(pd.Timestamp("2006-01-01"), hi * 1.01,
             f"历史最高 {hi:.0f}（{hi_date}）", fontsize=9, color="gray")
    ax1.scatter([pd.Timestamp(cur_date)], [cur], s=40, zorder=5, color="#b03030")
    ax1.annotate(f"今 {cur:.0f}\n分位 {pos_pct:.0f}%",
                 (pd.Timestamp(cur_date), cur),
                 xytext=(-120, 18), textcoords="offset points", fontsize=9,
                 arrowprops=dict(arrowstyle="->", color="0.5"))
    ax1.set_ylabel("点位")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.3)

    ax2.plot(pd.to_datetime(dy.index), dy, lw=0.8, color="#1f6fb0", label="股息率2")
    ax2.axhline(cur_dy, color="gray", ls="--", lw=1)
    ax2.text(pd.Timestamp(dy.index[0]), cur_dy * 1.02,
             f"今 {cur_dy:.2f}%（经验中枢 4~5.5%，越高越便宜）", fontsize=9, color="gray")
    ax2.set_ylabel("股息率 %")
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(alpha=0.3)

    out = DATA_DIR / f"hongli_valuation_{datetime.now():%Y%m%d}.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"📊 图已保存：{out}")


if __name__ == "__main__":
    main()
