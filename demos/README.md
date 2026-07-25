# demos/ — 学习示例（按计划顺序做的练习，留着随时回看）

> 这些是**学习过程产物**，每个对应一个知识点。日常回测请用根目录的 `run.py`。
> 运行方式：**在项目根目录**下 `python demos/文件名.py`
> （文件头部有 2 行路径引导，让根目录的轮子 fetch_data 等可以 import；
> 输出图片固定写到根目录 `data/` 下）。

| 文件 | 演示什么 | 对应知识 |
|---|---|---|
| `exit_rules_demo.py` | 移动止盈/跌破均线/一直持有，在半导体基金 2026 行情和腾讯 2021 大顶两个真实片段中的表现 | [Knowledge/exit_rules.md](../Knowledge/exit_rules.md) |
| `fund_nav_demo.py` | 场外基金净值拉取 + 与沪深300 归一化对比 + 风险指标速览 | [Knowledge/funds.md](../Knowledge/funds.md)、计划 04 |
| `tencent_week_kline.py` | 课程 K 线画法复刻：腾讯近一周日 K（含当日实时快照补一根） | 计划 01 数据轮子验收 |
