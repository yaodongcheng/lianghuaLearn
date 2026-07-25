# archive/ — 冻结的历史实验脚本（一行不改，仅存档）

> 2026-07-25  plans/07 回测框架抽取后归档。这些脚本是知乎策略验证（计划 06）的
> 过程产物，其可复用部分已抽进 `quant/` 包（引擎/信号/离场/指标/评估）。
> **新实验请用 `run.py` + `quant/`，不要在这里改代码。**

| 文件 | 内容 | 可复用部分的去向 |
|---|---|---|
| `zhihu_strategy1_verify.py` | v1：规律核查 + 深回撤回测 | 历史档案 |
| `zhihu_strategy1_oversold.py` | v2：短期超跌反弹回测 | 历史档案 |
| `zhihu_strategy1_oversold_v3.py` | v3：超跌指标对比 + 止盈方式对比 | ⭐ **回归基准**：`test_framework.py` 逐笔对比它以验证框架正确 |
| `oversold_mechanism_analysis.py` | v4：超跌机制分析 | 历史档案 |

## 如何重跑

- v1 / v2 / v3：项目根目录下 `python -m archive.<文件名去掉.py>`（包内 `from fetch_data import ...` 能正常解析）
- v4 注意：它写的是 `from zhihu_strategy1_oversold_v3 import ...`（按同目录脚本的方式 import），
  归档后重跑需先把该行改成 `from archive.zhihu_strategy1_oversold_v3 import ...`。
  按"一行不改"的归档原则我们没有改它——v4 不是回归基准，不需要被框架测试引用。
