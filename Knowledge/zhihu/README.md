# 知乎网文策略 → 本项目落成物（对照表）

> 这个目录存**原文原样**（不改一字，便于事后核对作者到底怎么说的）。
> 文章名与代码文件名不一定同名（历史上出过笔误），所以对照关系统一看这张表。
> 翻译流程本身见 [../strategy_translation.md](../strategy_translation.md)。

| 原文 | 落成物（run.py 填这个名字） | 契约 | 验证计划 | 能否实盘（支付宝场外） |
|---|---|---|---|---|
| [吃超跌恐慌修复策略.md](吃超跌恐慌修复策略.md) | `quant/strategies/bias_oversold.py` 等 6 个超跌信号 + `bottom_reversal` | 单标的择时 | plans/06、09 | 部分可（低频，但需注意 7 天惩罚费） |
| [长周期均衡持有策略.md](长周期均衡持有策略.md)（作者调整版：纳指+红利+黄金+国债） | `quant/portfolios/longterm_balance.py` | 组合配置 | plans/16、17 | ✓ **可以**，本项目最贴近实盘的一个 |
| 同上（作者第一版：纳指+红利低波+黄金+**豆粕**） | `quant/portfolios/longterm_balance_v1.py` | 组合配置 | plans/16、17 | ✓ 可以，但作者本人认有过拟合嫌疑 |
| [波动ETF策略.md](波动ETF策略.md)（三档条件单网格） | `quant/grid.py` + `quant/portfolios/grid_3tier.py`（日频近似版）；盘中触价口径见 `analysis/analyze_grid_etf.py` | 组合配置（单标的分批+留现金） | plans/16、19 | ✗ 需券商场内账户 + 条件单 |
| [分红融资比策略.md](分红融资比策略.md)（全A 选股金标准） | 选名单 `analysis/analyze_dividend_financing.py` → 冻结名单配方 `quant/portfolios/dividend_ratio_top20.py` | 组合配置（买入持有） | plans/16、19 | ✗ 需 A股账户买 20 只个股 |

⚠ 历史笔误备忘（2026-07-28 更正）：`quant/portfolios/volatile_etf.py` 这个文件名曾经
装着"长周期均衡第一版"的内容（当初复制文章时张冠李戴），现已更名为
`longterm_balance_v1.py`。真正的"波动ETF策略"是网格 → `grid_3tier`。
