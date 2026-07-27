# 12 趋势+反弹混合策略（trend_bounce）

| | |
|---|---|
| 状态 | 已完成（结论：牛熊切换失败，由 13 核心-卫星承接） |
| 开始 | 2026-07-26 |
| 完成 | 2026-07-27 |

## 背景与目标

用户观察：bottom_reversal 只吃熊市恐慌修复，90% 时间空仓，没吃到牛市上涨，
资金利用率低。要求：混合策略，牛市吃趋势、熊市吃恐慌修复。

**设计**：入场时就定模式，离场跟着模式走——
- 趋势模式：收盘站上 MA60 首日入场，跌破 MA20 离场（趋势的钱，移动止盈家族）
- 反弹模式：bottom_reversal 原信号（RSI6≤25+中阳确认），+7% 止盈 / 30 日超期

## 验收标准

- [ ] 策略文件 quant/strategies/trend_bounce.py + 注册，过因果门禁
- [ ] **分解对比**：混合 vs 反弹单(bottom_reversal) vs 趋势单(MA60/MA20) 三栏，
      混合必须在卡玛上打过 bottom_reversal 单跑才算成功（资金利用率不是免费的）
- [ ] 参数扰动（MA60→40/80）平滑性检查
- [ ] 对照 backtest_checklist.md 自检（参数数上升，过拟合风险要明说）
- [ ] run.py 比选模式出图

## 笔记

（执行中补充）

## 结果（2026-07-27 完成）

- 策略实现为 [quant/strategies/bull_bear_hybrid.py](../quant/strategies/bull_bear_hybrid.py)（已注册，过因果门禁）
- 四轮实验结论：牛熊切换**失败**——上证牛市有三种性格（恐慌底/尖峰/慢牛），
  单一规则各抓一种，混合切换没有通吃解（commit 56fa9bf"尝试切换牛熊 但是失败了"）
- 论证过程转入 [Knowledge/hybrid_vs_core_satellite.md](../Knowledge/hybrid_vs_core_satellite.md)
- 结论直接催生计划 13（核心-卫星组合）："一直在场 + 恐慌增强"才是通吃结构
- 验收标准中"混合必须在卡玛上打过 bottom_reversal"一项：实验已证明不成立，随结论关闭
