# -*- coding: utf-8 -*-
"""
run.py — 回测实验台（plans/07 交付物）。日常唯一要改的文件，只改下面两行。

用法：
    改下面两行 → python run.py
    或命令行覆盖：python run.py 贵州茅台 --strategy crash_10d

三种典型操作（plans/07 用户接口节）：
    换标的/换策略跑        → 改下面 TARGET / STRATEGY 两行
    同一入场对比几种离场   → 解开 EXIT_OVERRIDE 注释（不动策略文件）
    新写一个策略           → quant/strategies/ 新建文件 + __init__.py 登记两行
"""
import sys

# ================= 只改这里 =================
TARGET   = "上证指数"          # ① 标的：指数名/股票名/基金名/代码
STRATEGY = "bias_oversold"     # ② 策略：quant/strategies/ 里登记的名字
# （可选）EXIT_OVERRIDE：临时换离场做对比实验
# from quant import ExitSpec
# EXIT_OVERRIDE = ExitSpec(trail_activate=0.03, trail_pct=0.03, max_hold=20)
EXIT_OVERRIDE = None
# ============================================

START = "2018-07-01"     # 回测起点（数据从 2018-01 开始取，之前是指标预热段）
COST = 0.001             # 双边成本各 0.1%（ETF 无印花税口径）

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    target, strategy = TARGET, STRATEGY
    args = sys.argv[1:]
    if "--strategy" in args:                       # CLI 覆盖策略名
        i = args.index("--strategy")
        strategy = args[i + 1]
        args = args[:i] + args[i + 2:]
    if args:                                       # CLI 覆盖标的
        target = args[0]

    from quant.report import run_experiment
    run_experiment(target, strategy, start=START, exit_override=EXIT_OVERRIDE, cost=COST)
