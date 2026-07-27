# analysis/ — 分析脚本目录（一个计划一个可重跑脚本）

> 2026-07-27 设立（用户决策）：根目录的 analyze_*.py 累积到 7 个后统一收编于此。
> 与 `archive/` 的区别：archive 是**冻结**的历史档案（一行不改）；
> 本目录是**活着的**分析工具，结论过期时可以改、可以重跑。

## 约定

- **一个计划产出一个脚本**，命名 `analyze_*.py`（compare_index_bias.py 是
  计划体系建立前的历史命名，维持不改）
- 脚本头部的 docstring 写明：回答什么问题、方法纪律（参数是否原样）、用法
- 产出图一律存 `data/`（PNG 不进本目录）
- 脚本内有 sys.path 引导（把项目根目录加进 import 路径），
  所以**必须在项目根目录下运行**：`python analysis/analyze_xxx.py`

## 清单

| 脚本 | 计划 | 回答的问题 |
|---|---|---|
| analyze_fund_rotation.py | 04 | 场外基金动量轮动：费率/频率/空窗实验矩阵 |
| analyze_tencent_exit.py | 05 | 腾讯（00700）卖出时机：趋势状态 + 卖出规则情景模拟 |
| analyze_bottoms.py | 09 | 上证 8 个局部底部的量价特征四表 |
| analyze_core_satellite.py | 13 | 核心-卫星组合回测（核心持有 + 卫星抄底） |
| analyze_bottom_vol.py | 14 | bottom_reversal 多标的横测：波动率适配性证伪 |
| analyze_trend_fit.py | 15 | 策略×标的人格匹配矩阵（趋势型标的该用什么策略） |
| compare_index_bias.py | （早期） | bias_oversold 策略 × 六大宽基指数横向对比 |
