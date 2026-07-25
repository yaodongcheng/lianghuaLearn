# -*- coding: utf-8 -*-
"""
plot_kline.py — 读取 data/ 缓存画 K 线图，人工检查数据质量（计划 01 第 3 步）

用法：
    python plot_kline.py data/hk_00700_qfq.csv

输出两张图（存在数据文件同目录）：
    ① 近一年日 K 线（带成交量、5/10/20 日均线）→ 看细节、缺口
    ② 全区间收盘价曲线 → 看整体趋势、量级是否合理
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 无界面后端：只存图片文件，不弹窗
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

# 复用 wheels.md 的「A股配色 K 线样式」轮子（红涨绿跌 + 点划线网格 + 中文字体）
my_color = mpf.make_marketcolors(
    up="r", down="g", edge="i", wick="i",
    volume={"up": "red", "down": "green"}, ohlc="i",
)
my_style = mpf.make_mpf_style(
    marketcolors=my_color,
    gridaxis="both", gridstyle="-.",
    rc={"font.family": ["SimHei", "Microsoft YaHei"]},  # 中文字体，双保险
)


def plot_kline(csv_path, last_n=250):
    csv_path = Path(csv_path)
    df = pd.read_csv(csv_path, parse_dates=["date"])

    # mplfinance 要求：日期设为索引，列名严格 Open/High/Low/Close/Volume（大小写敏感）
    k = df.set_index("date").rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })

    # ① 近一年 K 线：蜡烛图 + 均线 + 成交量
    out1 = csv_path.with_name(csv_path.stem + "_kline.png")
    mpf.plot(
        k.tail(last_n), type="candle", style=my_style, volume=True,
        figsize=(14, 7), title=f"{csv_path.stem} K线（近{last_n}个交易日）",
        mav=(5, 10, 20), savefig=dict(fname=out1, dpi=120, bbox_inches="tight"),
    )

    # ② 全区间收盘曲线：一眼看 6 年趋势和量级
    out2 = csv_path.with_name(csv_path.stem + "_close.png")
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(k.index, k["Close"], linewidth=1)
    ax.set_title(f"{csv_path.stem} 全区间收盘价")
    ax.grid(True, linestyle="-.", alpha=0.5)
    fig.savefig(out2, dpi=120, bbox_inches="tight")
    plt.close(fig)

    print(f"已保存：{out1}")
    print(f"已保存：{out2}")


if __name__ == "__main__":
    plot_kline(sys.argv[1] if len(sys.argv) > 1 else "data/hk_00700_qfq.csv")
