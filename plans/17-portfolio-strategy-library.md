# 17-组合策略库：run.py 支持自由测组合（决策函数契约）

## 背景与动机

计划 16 把知乎三个策略都验完了，但**组合回测的能力锁死在分析脚本里**：
`analysis/analyze_zhihu_portfolios.py` 把成分、权重、阈值、报告、图全写在一个文件里，
想换配方（例如"红利换成红利低波""国债权重加到 40%""改成每年再平衡"）就得改分析代码。

用户要的是**和单标的策略一样的自由度**：run.py 填两行就能跑一个组合。

## 关键设计决策（用户拍板，重要）

第一版我做成了"配置表"式的 `Portfolio(holdings, weights, threshold)`——用户当场否掉：
那不是策略，只是参数，换个打法（网格、定投、动量轮动）就塞不进去了。

正确的抽象是**把单标的的契约升一维**：

| | 策略给什么 | 引擎给什么 |
|---|---|---|
| 单标的（择时） | `entry_fn(df)->bool` + `exit_fn(...)->str\|None`（今天买不买/卖不卖） | T+1 开盘成交、扣成本、记账 |
| 组合（配置） | `decide_fn(ctx)->{标的: 带符号金额}`（今天每只买多少/卖多少钱） | T+1 收盘成交、先卖后买、扣成本、记账 |

为什么组合只用**一个**决策函数而不是"买函数+卖函数"：组合调仓同一天必然同时有买有卖
（卖超配的、买低配的），拆成两个函数反而要在外面同步它们。

这样"阈值再平衡"只是**其中一种**决策函数，以后写网格/定投/动量轮动都是同一个契约、
同一个引擎——继承原有分层，没有第二套体系。

## 交付物

- [x] `quant/rebalance.py`（③ 决策层，与 signals.py/exits.py 平级）：决策函数工厂
      `threshold_rebalance` / `buy_and_hold` / `periodic_rebalance`，都带
      `.desc/.factory/.params` 标签供报告回显与参数扫描
- [x] `quant/portfolio.py`（④ 引擎层）重写为通用事件循环：`PortfolioContext` 快照
      + T+1 成交 + 先卖后买 + 买不超现金/卖不超持仓截断 + 成交日志
- [x] `quant/portfolios/`（③ 策略层）组合配方库 + 注册表：
      `longterm_balance` / `longterm_balance_v1` / `gold_nasdaq_2`（模板+消融实验）
      ⚠ `longterm_balance_v1` 在本计划期间叫 `volatile_etf`，2026-07-28 计划 19 更名
      （原名是笔误；真正的"波动ETF策略"是网格 → `grid_3tier`）
- [x] `quant/report_portfolio.py`（⑤）：三要素回显 + 绩效表（本策略/不再平衡对照/
      沪深300 基准）+ 成交明细 + 权重漂移 + 阈值敏感性 + 样本量警报
- [x] `quant/plot_portfolio.py`（⑤）：单配方三联图（净值/权重漂移+▼调仓/再平衡净贡献）
      + 多配方比选图
- [x] `run.py`：按名字自动分派（名字在 portfolios 注册表 → 组合模式，TARGET 忽略），
      名单=比选模式，`PORTFOLIO_OVERRIDE` 临时换决策规则不动配方文件
- [x] `test_portfolio.py` 扩到 9 项全绿
- [x] 旧调用方跟进：`analysis/analyze_zhihu_portfolios.py` 瘦成薄壳、
      `analysis/analyze_dividend_financing.py` 改用 `buy_and_hold`、wheels.md 换签名

## 踩坑：模块行数上限逼出的拆分（2026-07-28）

首版写完 `python test_framework.py` 挂了 2 项——不是逻辑错，是框架自己的第 6 项体检
「quant/ 每模块 <150 行」：`portfolio.py` 195 行、`report_portfolio.py` 190 行。
这条限制的用意是**逼迫职责单一**（一个文件一屏读完），所以按职责拆而不是抬上限：

| 原文件 | 拆成 | 各自的职责 |
|---|---|---|
| portfolio.py 195 行 | `portfolio.py` 125 + `portfolio_data.py` 93 | 循环（钱怎么动） / 桌面（取数、日期对齐、今日快照 PortfolioContext） |
| report_portfolio.py 190 行 | `report_portfolio.py` 107 + `report_portfolio_parts.py` 103 | 总装顺序 / 每块报告怎么算怎么打印 |

`portfolio.py` 里保留一行转出（`from quant.portfolio_data import ...` + `__all__`），
所以 `from quant.portfolio import load_portfolio_navs, align_prices` 的老写法不破。
拆完 `test_framework.py` / `test_portfolio.py` 全绿，实盘数字**一个没变**
（longterm_balance 期末仍 38851 / 年化 +11.08% / 回撤 -12.9% / 92 次调仓）——
纯搬家、零行为变化，这也是重构该有的样子。

## 验证：复现计划 16 的数字（防重构改错）

| 口径 | plans/16（旧引擎） | 本次（新契约） | 差异原因 |
|---|---|---|---|
| longterm_balance 期末 | 38788 元 / +11.07% / -13.0% | 38851 元 / +11.08% / -12.9% | 建仓改为 T+1 成交，晚一天 |
| ③ 不再平衡对照 | 39829 元 / +11.30% / -20.4% | 39798 元 / +11.28% / -20.6% | 同上 |
| volatile_etf（今 longterm_balance_v1） | 23324 元 / +13.87% / -10.2% | 23495 元 / +13.98% / -10.4% | 同上 |

差异均来自一处**修正**：旧引擎在回测第一天收盘直接按目标权重建仓（用了当天收盘价，
等于"决策和成交同一时刻"）；新引擎第一天只决策、第二天成交，与之后所有调仓同一纪律。

## 新实验结论（本计划顺手得到的）

- `gold_nasdaq_2`（纳指+黄金 50/50，2020-01 起同期）：年化 +16.15%，但回撤 -16.8%、
  夏普 0.91 < longterm_balance_v1（原 volatile_etf）的 1.17 → **少两条腿收益更高但更晃**，红利+债券买的是稳。
- `periodic_rebalance(freq="Y")` 换掉阈值触发（长周期均衡，同区间）：
  年化 10.89%（vs 11.08%）、回撤 -16.3%（vs -12.9%）、调仓 13 次（vs 92 次）
  → **省了 79 次手续费却多了 3.4 个点回撤**：阈值触发的价值在"歪了就修"，
  定期再平衡在两次调仓之间可能歪很久没人管。

## 自检清单对照（backtest_checklist.md）

- **未来函数**：① `ctx.hist` 只切到决策日（自检⑧逐日核对 59 天）；② 订单一律 T+1
  成交，成交价决策时未知（自检③）；③ 多标的对齐只 ffill（向前填充=用已知的过去）✓
- **过拟合**：参数全来自原文，零调参；阈值 2%/3%/5%/10% 扫描年化 11.01~11.09%
  → 不依赖参数点 ✓
- **成本**：双边各 0.1%，建仓也扣；总成本 96.9 元占本金 0.97% 已披露；
  <7 天间隔调仓 4 次的 1.5% 惩罚费差额未计入，报告明确提示 ✓
- **账目守恒**：自检① 与手算加权净值逐日相符（1e-8 内）✓
- **不许透支/裸卖空**：自检⑦ 引擎自动截断（这是"回测能做到的实盘也得能做到"）✓
- **样本量**：再平衡 92 次（③）够用；<10 次时报告自动警报 ✓
- **未处理**：场外基金申赎确认时滞（T+1 净值已近似）、QDII 的 T+2、
  联接基金现金留存导致的跟踪偏差（口径已在配方文件写明）

## 收尾：按新纪律清查本次 diff（2026-07-28）

框架和翻译流程立起来之后，回头审了一遍这批改动里"不符合纪律的代码"，修了 4 处：

| 问题 | 违反的纪律 | 怎么修的 |
|---|---|---|
| `analyze_dividend_financing.py` 直接 `import akshare` 逐股查 IPO（带缓存+重试的逻辑写在分析脚本里） | 取数一律走 fetch_data 轮子 | 抽成 `fetch_data.fetch_ipo_amount(codes, as_of)`，脚本里只剩 5 行薄包装；轮子登记进 wheels.md（含"静默失败=篡改"那条坑） |
| 两个分析脚本各自手写绩效表格行（年化/回撤/夏普的格式化） | 绩效口径单一来源（规则 3） | 统一用 `report_portfolio_parts.perf_row`；基准取数/对齐/缩放用 `load_bench` |
| `run.py` 比选模式下 `PORTFOLIO_OVERRIDE` 被静默忽略 | 改了参数没生效 = 假结果 | 用错模式直接 `SystemExit` 报错并说明原因（`EXIT_OVERRIDE` 在组合模式同样报错） |
| 三个新分析脚本没登记 `analysis/README.md`；网格脚本没写"为什么不走框架" | 文档维护规则 + 新规则 7 | README 补三行清单 + 一节"什么情况才该新写脚本"；网格脚本 docstring 加 ⚠ 段说明它属于"盘中触价成交"那类 |

留了一处**没在本计划改**：策略净值 vs 基准的归一化对比图在 `quote.py` 和两个分析脚本里
共三份重复实现 → 抽轮子要动 `quote.py`（用户日常工具），单开 [plans/18](18-bench-compare-plot-wheel.md)。

修完重跑验证：`test_framework.py` / `test_portfolio.py` 全绿，两个分析脚本
输出数字与改造前一致（网格科创50 期末 15343 元、分红融资比 top20 年化 +9.54%）。

## 状态：已完成（2026-07-28）
