# -*- coding: utf-8 -*-
"""
demos/oversold_vs_bear_year.py — 熊市压力测试：超跌策略遇上股灾会怎样？

起因：用户看完「吃超跌恐慌修复策略」后提出质疑——
"这个策略最大问题是如何判断是否到了底部？就祈祷别遇上股灾吧"

这个脚本不预测底部，只回答一个事实问题：
回测区间里就有一段真实股灾（2018 年上证全年 -24.6%，3587 → 2449 单边阴跌一年），
策略在那段日子里实际做了什么、每笔亏赚多少？

方法：
1. 框架标准回测（bias_oversold：BIAS20≤-6% 买，+5% 止盈 / 20 日时间止损）
2. 每笔交易标注买入当天的市场环境：距 250 日高点回撤（衡量"当时已经跌成什么样"）
3. 按自然年汇总：策略当年收益 vs 当年指数涨跌

自检（对照 Knowledge/backtest_checklist.md）：
- 信号 T 日收盘出 → T+1 开盘成交，无未来函数（引擎强制，本脚本无绕过手段）
- "按年分组"只是事后展示统计，不参与任何交易决策——展示口径与交易口径分离
- 市场环境列（距 250 日高点回撤）只用买入日当天及以前的数据计算，同样因果
- 数据多取 2017 全年做指标预热段，回测从 2018-01-01 开始（2018 股灾全程在考场内）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 让根目录的 quant 包可 import

import pandas as pd

from quant.data import load_data
from quant.engine import run_backtest_ex
from quant.strategies import REGISTRY

START = "2018-01-01"     # 回测起点：2018 股灾完整在区间内
COST = 0.001             # 双边成本各 0.1%（ETF 口径）
STRATEGY = "bias_oversold"


def market_env(df, buy_date):
    """买入当天的市场环境（只用到当天及以前的数据，因果安全）：
    距 250 日高点回撤 —— 衡量"买的时候市场已经跌成什么样了"。
    """
    hist = df.loc[:buy_date, "close"].tail(250)
    return df.loc[buy_date, "close"] / hist.max() - 1


def analyze(target):
    df, info = load_data(target, start="20170101")   # 2017 全年做预热段
    strategy = REGISTRY[STRATEGY]
    exit_fn = strategy.exit.to_fn()
    trades, eq, _tail = run_backtest_ex(df, strategy.entry_fn, exit_fn,
                                        start=START, cost=COST)
    bt = df.loc[pd.Timestamp(START):]
    idx_ret = bt["close"].iloc[-1] / bt["close"].iloc[0] - 1

    print(f"\n{'=' * 80}")
    print(f"{info['name']} × {STRATEGY}（BIAS20≤-6% 买，+5% 止盈 / 20 日时间止损）")
    print(f"回测 {bt.index[0]:%Y-%m-%d} ~ {bt.index[-1]:%Y-%m-%d}，期间指数本身 {idx_ret:+.1%}")
    print(f"{'=' * 80}")

    if not len(trades):
        print("区间内无交易（信号从未触发）")
        return

    t = trades.copy()
    t["距250日高点"] = [f"{market_env(df, d):+.0%}" for d in t["买入日"]]
    t["收益率"] = (t["收益率"] * 100).round(1).astype(str) + "%"
    print("\n逐笔交易（「距250日高点」= 买入当天市场已从近一年高点跌了多少）：")
    print(t[["买入日", "卖出日", "持有交易日", "收益率", "卖出原因", "距250日高点"]]
          .to_string(index=False))

    # —— 按自然年汇总：策略当年收益（净值曲线口径） vs 当年指数涨跌 ——
    tr = trades.copy()
    tr["年份"] = pd.to_datetime(tr["买入日"]).dt.year
    yearly_idx = bt["close"].groupby(bt.index.year).apply(lambda s: s.iloc[-1] / s.iloc[0] - 1)
    yearly_eq = eq.groupby(eq.index.year).apply(lambda s: s.iloc[-1] / s.iloc[0] - 1)

    print("\n按年汇总（策略收益 = 当年净值曲线涨跌，含空仓期按 0 波动计）：")
    print(f"{'年份':<8}{'交易':>4}{'平均每笔':>10}{'策略当年':>10}{'指数当年':>10}")
    for y in sorted(set(tr["年份"]) | set(yearly_idx.index)):
        g = tr[tr["年份"] == y]
        n = len(g)
        avg = f"{g['收益率'].mean():+.1%}" if n else "—"
        eq_y = f"{yearly_eq.get(y, 0):+.1%}"
        idx_y = f"{yearly_idx.get(y, float('nan')):+.1%}"
        print(f"{y:<10}{n:>4}{avg:>10}{eq_y:>10}{idx_y:>10}")

    worst_i = trades["收益率"].idxmin()
    print(f"\n最惨一笔：{trades.loc[worst_i, '买入日']} 买入，{trades.loc[worst_i, '收益率']:+.1%}"
          f"（{trades.loc[worst_i, '卖出原因']}）")
    print(f"亏损笔数：{(trades['收益率'] < 0).sum()} / {len(trades)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 中文控制台默认 GBK
    analyze("上证指数")
    analyze("沪深300")
