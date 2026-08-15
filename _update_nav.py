# -*- coding: utf-8 -*-
"""临时脚本：更新四只基金的净值缓存"""
from fetch_data import fetch_fund_nav

codes = ["539001", "090010", "000216", "161119"]
for code in codes:
    print(f"--- 更新 {code} ---")
    df = fetch_fund_nav(code, force_refresh=True)
    print(f"  行数: {len(df)}, 最新: {df['date'].max()}, 最新净值: {df['nav'].iloc[-1]:.4f}")
print("全部更新完成")
