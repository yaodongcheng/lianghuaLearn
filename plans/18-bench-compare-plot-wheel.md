# 计划 18：抽出"净值 vs 基准"归一化对比图轮子

状态：待规划（2026-07-28 从计划 17 的纪律清查中拆出）

## 为什么要做

同一张图（策略净值 vs 一个或多个基准，都除以起点值归一化后画在一起）现在有**三份代码**：

| 位置 | 用途 |
|---|---|
| `quote.py:_plot_return_compare` | 用户随手查行情时的对比图 |
| `analysis/analyze_dividend_financing.py:report_and_plot` | top20 组合 vs 沪深300/中证500 |
| `analysis/analyze_grid_etf.py:plot` 下半张 | 网格净值 vs 买入持有 |

按 CLAUDE.md 的轮子纪律（"2 个及以上场景用到就收进 wheels.md"），三份就该抽了。
不趁计划 17 顺手改的原因：要动 `quote.py`（用户日常在用的工具），改坏了影响手感，
单独一个计划、单独验证更稳妥。

## 目标

`quant/plot_compare_bench.py` 提供一个函数，签名大致：

```python
plot_bench_compare(series_map, title, path, base=None, ax=None)
# series_map: {"标签": pd.Series(净值或价格)}；第一条默认当主角（红色粗线）
# base: 归一化基准日（None=各自第一个有效值）；ax: 传入则画在现有子图上（网格脚本要用）
```

要求：
1. 中文字体/负号设置只在一处（现在三个文件各写一遍 `rcParams`）
2. 支持"画进现有 ax"，否则网格脚本的双子图布局用不了
3. 三处调用点全部改成调它，出图与改造前**肉眼一致**（对比新旧 PNG）

## 验收

- [ ] 三个调用点改完，`python quote.py 沪深300`、两个 analysis 脚本各跑一遍，PNG 正常
- [ ] `python test_framework.py` 全绿（新模块 < 150 行）
- [ ] wheels.md 把"基准对比画图"从"待补充"移入正式条目
