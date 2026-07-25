# -*- coding: utf-8 -*-
"""
tencent_week_kline.py — 用课程文件 lianghuaLearn.py 里 testPandas_mplfinance() 的画法，
画腾讯 00700.HK 最近一周的日 K 线。

目的：验证数据接口（fetch_daily）拉任意小区间也好用，并和课程学的画法接上。
说明：课程函数 testPandas_mplfinance() 内部写死了读 demo.csv，没法直接喂腾讯数据，
     所以这里把它的【流程和样式】完整复刻过来（列名处理 → 统计 → 涨跌幅 → 同款样式画图）。
"""

import matplotlib
matplotlib.use("Agg")  # 无界面后端：存 PNG 不弹窗（课程里是 plt.show() 弹窗）

import mplfinance as mpf
import pandas as pd

from fetch_data import fetch_daily, fetch_spot_bar

# ============================================================
# 第 1 步：用计划 01 的轮子接口拉"最近一周"数据
# force_refresh=False：缓存新鲜就直接读本地（秒回）；想拿最新一根就改 True 重新下载
# ============================================================
df = fetch_daily("hk", "00700", start="20260715", force_refresh=False)

# 日 K 线接口是批量更新，港股收盘后数小时才有当天数据；
# 收盘后想立刻看当日行情，用实时快照补一根（只在内存补，不写缓存）
spot = fetch_spot_bar("00700")
daily_latest = df["date"].max()
if spot["date"].iloc[0] > daily_latest:
    df = pd.concat([df, spot], ignore_index=True)
    print(f"（日K线最新只到 {daily_latest:%m-%d}，已用实时快照补上当日 "
          f"{spot['date'].iloc[0]:%m-%d} 一根）")

print(f"拉到 {len(df)} 根 K 线：")
print(df.to_string(index=False))

# ============================================================
# 第 2 步：完全按课程 testPandas_mplfinance() 的流程处理
# （课程的列名是 end_price/open_price/...，我们的统一列名是 close/open/...，含义一一对应）
# ============================================================
df["date"] = pd.to_datetime(df["date"])
df.set_index("date", inplace=True)

# 添加年月日信息（课程里的可选步骤，照搬）
df["year"] = df.index.year
df["month"] = df.index.month
df["day"] = df.index.day

# 打印统计信息（照搬课程的统计，end_price 对应我们的 close）
print(f"\nclose min : {df['close'].min()}, close max : {df['close'].max()}, "
      f"close mean : {df['close'].mean():.2f}")
print(f"month close mean :\n{df.groupby('month')['close'].mean()}")

# 计算涨跌幅（照搬课程）
df["rise"] = df["close"].diff()
df["rise_ratio"] = df["close"].pct_change()

# mplfinance 要求列名必须为 Open, High, Low, Close, Volume（大小写敏感）
df.rename(columns={
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}, inplace=True)

# ============================================================
# 第 3 步：课程原版样式（make_marketcolors + make_mpf_style，一字未改）
# ============================================================
my_color = mpf.make_marketcolors(
    up='r',           # 阳线红色（涨）
    down='g',         # 阴线绿色（跌）
    edge='i',         # 边框颜色继承自 up/down
    wick='i',         # 影线颜色继承
    volume={'up': 'red', 'down': 'green'},  # 成交量条颜色
    ohlc='i'          # OHLC 标记颜色继承（用于线型图）
)

my_style = mpf.make_mpf_style(
    marketcolors=my_color,
    gridaxis='both',   # 双轴网格
    gridstyle='-.',    # 点划线
    rc={'font.family': ['SimHei', 'Microsoft YaHei']}
    # 课程写的是 'ST Song'（Mac 字体），这台 Windows 没有；matplotlib 会预检列表里
    # 每个字体并对缺失者逐条刷警告，所以这里只留 Windows 实际安装的字体
)

# ============================================================
# 第 4 步：画 K 线（参数与课程一致：candle + volume + mav=(5,10) + figsize=(12,6)）
# 注意：只有约 5 个交易日，MA5 只够算出 1 个点、MA10 出不来——这不是 bug，
#       是均线窗口比数据还长的必然结果。
# ============================================================
out = "data/hk_00700_week_kline.png"
mpf.plot(df, type='candle', style=my_style, volume=True, figsize=(12, 6),
         title='tencent 00700.HK weekly K-line', ylabel='Price',
         ylabel_lower='Volume', mav=(5, 10),
         savefig=dict(fname=out, dpi=120, bbox_inches='tight'))
print(f"\n已保存：{out}")
