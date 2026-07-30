# -*- coding: utf-8 -*-
"""
run.py — 回测实验台（plans/07 + plans/17 交付物）。日常唯一要改的文件，只改下面两行。

用法：
    改下面两行 → python run.py
    或命令行覆盖：python run.py 贵州茅台 --strategy crash_10d
                  python run.py --strategy longterm_balance        （组合模式不用填标的）

两种模式，按名字自动分派（名字在哪个注册表里就走哪个模式，不会认错）：
    单标的择时  策略名在 quant/strategies/  → 用 TARGET 那只标的，出文字报告+买卖点图
    多标的组合  组合名在 quant/portfolios/  → 成分写在配方文件里，TARGET 自动忽略

产出：终端文字报告 + PNG（data/trades_*.png 或 data/portfolio_*.png，固定名覆盖更新）

四种典型操作：
    换标的/换策略跑        → 改下面 TARGET / STRATEGY 两行
    同一入场对比几种离场   → 解开 EXIT_OVERRIDE 注释（不动策略文件）
    同一配方换再平衡打法   → 解开 PORTFOLIO_OVERRIDE 注释（不动配方文件）
    新写一个策略/组合      → quant/strategies/ 或 quant/portfolios/ 新建文件 + 登记两行
"""
import sys

# ================= 只改这里 =================
TARGET   = "fund:100053"       # ① 标的：指数名/股票名/基金名/代码（组合模式下忽略）
# ⚠ 单标的实验请优先写**买得到的东西**（支付宝场外基金代码 / ETF），别写"上证指数"：
#   a) 你没有 A股账户，指数本身买不了，跑出来的收益不可执行；
#   b) 上证指数是**价格指数**（成分股分红后指数直接往下掉，不含股息），而基金净值
#      把分红做了再投资 → 同期买入持有：上证指数 +37.4%，富国上证指数联接A(100053)
#      +76.0%（2018-07~2026-07）。拿指数回测的收益去估基金，会系统性低估。
#   指数只在"研究市场本身"（找底部特征、算涨跌统计）时才该用。
#STRATEGY = [ "bottom_reversal"]
STRATEGY = ["longterm_balance"]
# ② 填策略名 或 组合名。**一个名字用 list 也行**：["longterm_balance"] = 单个跑
#    （完整报告+图）；两个及以上 = 比选模式（对比表+对比图，自动带沪深300基准）
#    单标的策略：quant/strategies/ 里的名字（bias_oversold / bottom_reversal / macd_cross ...）
#    组合配方：  quant/portfolios/ 里的名字（longterm_balance / grid_3tier /
#                dividend_ratio_top20 / bottom_reversal_fund ...）
#    ⚠ 名单里不能混搭两类名字；择时策略要进组合比选，用 quant/adapter.py 包成配方

# （可选）临时换规则做对比实验，不动策略/配方文件。单标的用 EXIT_OVERRIDE、组合用
# PORTFOLIO_OVERRIDE（用错模式会直接报错，不会静默忽略）。用法见 quant/exits.py、
# quant/rebalance.py 的文档串。
EXIT_OVERRIDE = None
PORTFOLIO_OVERRIDE = None
# ============================================

START = "2026-07-01"      # 回测起点（单标的和组合共用）；None = 组合模式自动取全部成分都有数据的首日
COST = 0.001              # 双边成本各 0.1%（ETF 无印花税口径）
INITIAL = 10000.0         # 组合模式初始资金（元）

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    target, strategy = TARGET, STRATEGY
    args = sys.argv[1:]
    if "--strategy" in args:                       # CLI 覆盖策略/组合名（逗号分隔=比选）
        i = args.index("--strategy")
        strategy = args[i + 1]
        args = args[:i] + args[i + 2:]
    if args:                                       # CLI 覆盖标的
        target = args[0]

    names = [s.strip() for s in strategy.split(",")] if isinstance(strategy, str) \
        else [str(s).strip() for s in strategy]
    # 文件里推荐写 list（["a", "b"]）；字符串分支是为了 CLI——命令行只能传字符串，
    # 所以 --strategy a,b 这种逗号写法必须继续支持。
    if len(set(names)) != len(names):                # 重名 → 报表两行同名没法读
        raise SystemExit(f"STRATEGY 里有重复的名字：{names}")
    if not names:
        raise SystemExit("STRATEGY 是空的：填一个策略名或组合名")

    from quant.portfolios import REGISTRY as PORTFOLIOS
    is_pf = [n in PORTFOLIOS for n in names]
    if any(is_pf) and not all(is_pf):               # 混搭 → 明确报错，不猜
        raise SystemExit(f"不能混搭组合名和单标的策略名：组合 "
                         f"{[n for n, f in zip(names, is_pf) if f]}、"
                         f"策略 {[n for n, f in zip(names, is_pf) if not f]}")

    if all(is_pf):                                  # ===== 组合模式（多标的配置）=====
        # 覆盖参数用错模式时直接报错，不静默忽略——"改了没生效"是最难查的假结果
        if EXIT_OVERRIDE is not None:
            raise SystemExit("EXIT_OVERRIDE 只对单标的模式有效（组合没有满仓/空仓离场），"
                             "组合要换规则请用 PORTFOLIO_OVERRIDE")
        if len(names) == 1:
            from quant.report_portfolio import run_portfolio_experiment
            run_portfolio_experiment(names[0], start=START, cost=COST,
                                     initial_cash=INITIAL,
                                     decide_override=PORTFOLIO_OVERRIDE)
        else:
            if PORTFOLIO_OVERRIDE is not None:
                raise SystemExit("比选模式下不能用 PORTFOLIO_OVERRIDE：同一个决策函数套到"
                                 f"多个配方上，比的就不是配方本身了。要对比换规则的效果，"
                                 f"请把 STRATEGY 改成单个组合名分别跑，或在 "
                                 f"quant/portfolios/ 里把新规则登记成一个配方再进名单")
            from quant.report_portfolio import compare_portfolio_experiment
            compare_portfolio_experiment(names, start=START, cost=COST,
                                         initial_cash=INITIAL)
    else:                                           # ===== 单标的模式 =====
        if PORTFOLIO_OVERRIDE is not None:
            raise SystemExit("PORTFOLIO_OVERRIDE 只对组合模式有效（单标的引擎只有满仓/"
                             "空仓两态），单标的要换离场请用 EXIT_OVERRIDE")
        if len(names) == 1:                         # 单策略：完整报告 + 买卖点图
            from quant.report import run_experiment
            run_experiment(target, names[0], start=START,
                           exit_override=EXIT_OVERRIDE, cost=COST)
            from quant.plot import plot_experiment
            plot_experiment(target, names[0], start=START,
                            exit_override=EXIT_OVERRIDE, cost=COST)
        else:                                       # 比选：对比表 + 对比图
            from quant.plot_compare import plot_compare_experiment
            plot_compare_experiment(target, names, start=START,
                                    exit_override=EXIT_OVERRIDE, cost=COST)
