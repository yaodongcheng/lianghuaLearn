# -*- coding: utf-8 -*-
"""
analysis/analyze_bottoms.py — plans/09：8 个"局部底部"的 K 线组合 + 量价特征事后分析

在用户指定的 8 个窗口内找【最低收盘价】= 底部 T 日，输出四张表：
    A 底部定位（窗口 → 实际底部日期，检验用户给的月份准不准）
    B 底部特征（下跌段深度/恐慌度 + T 日及前后 K 线形态 + 量能）
    C 逐日明细（T-5 ~ T+5 的 K 线组合，肉眼找共性）
    D 反弹特征（最大反弹幅度/到达时间/见顶时的量价状态 → 离场设计依据）

⭐ 方法警告：这是事后分析（拿着答案找规律），提炼出的信号必须再过两道关才算数：
   1. 规则化（无未来函数）2. 全样本回测（看误报率，不是只看这 8 次）
"""
import sys
from pathlib import Path

# 脚本位于 analysis/ 子目录：Python 只把【脚本所在目录】加进 import 路径，
# 不会加项目根目录——手动补上，否则 from quant... / fetch_data 全部找不到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from quant.data import load_data
from quant.indicators import cal_bias, cal_rsi

# 用户指定的 8 个底部窗口（标签, 窗口起, 窗口止）——窗口略放宽，底部日期让数据自己说
WINDOWS = [
    ("2019底(用户:2月初)", "2019-01-01", "2019-02-28"),
    ("2020底(用户:3月下旬)", "2020-03-01", "2020-04-10"),
    ("2021底(用户:3月底)", "2021-03-01", "2021-04-10"),
    ("2022底(用户:3月)", "2022-03-01", "2022-03-31"),
    ("2023底(用户:3月)", "2023-03-01", "2023-03-31"),
    ("2024底(用户:2月)", "2024-01-15", "2024-02-29"),
    ("2025底(用户:4月)", "2025-04-01", "2025-04-30"),
    ("2026底(用户:4月)", "2026-04-01", "2026-04-30"),
]


def kline(df, i):
    """单日 K 线特征（全部只用当天及以前的数据）。
    涨幅/振幅/实体/下影都除以昨收，变成百分比可跨年比较；量比 = 当日量 / 20 日均量。"""
    r, pc = df.iloc[i], df["close"].iloc[i - 1]
    v20 = df["volume"].rolling(20).mean().iloc[i]
    return {
        "涨幅": r["close"] / pc - 1,
        "振幅": (r["high"] - r["low"]) / pc,
        "实体": (r["close"] - r["open"]) / pc,
        "下影": (min(r["open"], r["close"]) - r["low"]) / pc,
        "量比": r["volume"] / v20 if pd.notna(v20) and v20 > 0 else float("nan"),
    }


def pct(x, nd=1):
    return f"{x * +100:.{nd}f}%" if pd.notna(x) else "—"


def main():
    df, _ = load_data("上证指数")
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    rsi6, bias20 = cal_rsi(close, 6), cal_bias(close, 20)
    idx = df.index

    # ---------- A 表：底部定位 ----------
    bottoms = []  # (标签, T 的整数位置)
    print("\n===== A. 底部定位（窗口内最低收盘价 = T 日）=====")
    for label, w0, w1 in WINDOWS:
        seg = close.loc[w0:w1]
        t = seg.idxmin()                      # 收盘最低点
        t_low = low.loc[w0:w1].idxmin()       # 盘中最低点（常比收盘低晚 1 天，V 型特征）
        i = idx.get_loc(t)
        bottoms.append((label, i))
        print(f"{label:22s} → T={t:%Y-%m-%d} 收盘 {close.loc[t]:.0f}"
              f"（盘中最低日在 {t_low:%m-%d}，{low.loc[t_low]:.0f}）")

    # ---------- B 表：底部特征 ----------
    print("\n===== B. 底部特征（左=下跌段，中=T日K线/量能，右=指标位置）=====")
    hdr = (f"{'底部':24s}{'60日回撤':>9s}{'阴跌天数':>7s}{'近10日':>7s}{'恐慌日(5日内最惨)':>14s}"
           f"{'T日涨幅':>8s}{'T日振幅':>7s}{'T日下影':>7s}{'T日量比':>7s}"
           f"{'RSI6':>6s}{'BIAS20':>8s}")
    print(hdr)
    for label, i in bottoms:
        t = idx[i]
        hi60 = close.iloc[max(0, i - 60):i + 1].max()
        i_hi = close.iloc[max(0, i - 60):i + 1].values.argmax()
        days_from_hi = (60 - i_hi) if i >= 60 else None
        ret10 = close.iloc[i] / close.iloc[i - 10] - 1
        worst5 = min(close.pct_change().iloc[i - 4:i + 1])          # 5 日内最惨单日
        k = kline(df, i)
        print(f"{label:24s}{pct(close.iloc[i]/hi60-1):>9s}"
              f"{str(days_from_hi)+'天':>7s}{pct(ret10):>7s}{pct(worst5):>14s}"
              f"{pct(k['涨幅']):>8s}{pct(k['振幅']):>7s}{pct(k['下影']):>7s}"
              f"{k['量比']:>6.1f}x{rsi6.iloc[i]:>6.1f}{pct(bias20.iloc[i]):>8s}")

    # ---------- C 表：逐日明细（T-5 ~ T+5）----------
    print("\n===== C. 逐日明细（T-5 ~ T+5，◀=底部 T 日）=====")
    for label, i in bottoms:
        t = idx[i]
        print(f"\n--- {label}  T={t:%Y-%m-%d} ---")
        print(f"{'日期':12s}{'涨幅':>7s}{'振幅':>7s}{'实体':>7s}{'下影':>7s}{'量比':>6s}")
        for j in range(i - 5, min(i + 6, len(df))):
            k = kline(df, j)
            mark = " ◀ T" if j == i else ""
            print(f"{idx[j]:%Y-%m-%d}  {pct(k['涨幅']):>7s}{pct(k['振幅']):>7s}"
                  f"{pct(k['实体']):>7s}{pct(k['下影']):>7s}{k['量比']:>5.1f}x{mark}")

    # ---------- D 表：反弹特征（事后视角，供离场设计参考）----------
    print("\n\n===== D. 反弹特征（假设 T+1 开盘买入——真实可成交口径）=====")
    print(f"{'底部':24s}{'20日内最大浮盈':>13s}{'(第几天)':>8s}{'60日内最大浮盈':>13s}"
          f"{'(第几天)':>8s}{'+5%几天达成':>10s}{'拿满20天收益':>11s}{'峰值日RSI6':>9s}")
    med = {"m20": [], "m60": [], "d5": []}
    for label, i in bottoms:
        entry = df["open"].iloc[i + 1]                     # T+1 开盘（无未来函数成交价）
        seg20 = close.iloc[i + 1:i + 21]
        seg60 = close.iloc[i + 1:i + 61]
        m20, m60 = seg20.max() / entry - 1, seg60.max() / entry - 1
        d20 = seg20.values.argmax() + 1
        d60 = seg60.values.argmax() + 1
        hit5 = next((n + 1 for n, c in enumerate(seg20.values) if c >= entry * 1.05), None)
        r20 = seg20.iloc[-1] / entry - 1
        i_peak = i + 1 + int(seg60.values.argmax())
        med["m20"].append(m20); med["m60"].append(m60)
        if hit5: med["d5"].append(hit5)
        print(f"{label:24s}{pct(m20):>13s}{('第'+str(d20)+'天'):>8s}{pct(m60):>13s}"
              f"{('第'+str(d60)+'天'):>8s}{(str(hit5)+'天' if hit5 else '未达成'):>10s}"
              f"{pct(r20):>11s}{rsi6.iloc[i_peak]:>9.1f}")
    print(f"\n中位数：20日内最大浮盈 {pct(pd.Series(med['m20']).median())}，"
          f"60日内最大浮盈 {pct(pd.Series(med['m60']).median())}，"
          f"+5% 达成 {len(med['d5'])}/8 次（中位 {pd.Series(med['d5']).median():.0f} 天）")


if __name__ == "__main__":
    main()
