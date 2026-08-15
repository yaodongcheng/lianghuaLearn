# 项目：量化交易学习（lianghuaLearn）

## 用户画像（重要，影响所有回复方式）
- 用户是**炒股和量化交易的新手**，学过最基础的量化与技术分析课程，股票知识欠缺
- 交流语言：**中文**
- 投资背景（2026-07 记录）：
  - **没有 A股账户**，未来主要通过**支付宝买场外基金** → 策略最终要落在基金上（规则差异大，见 [Knowledge/funds.md](Knowledge/funds.md)）
  - 持有**腾讯（00700.HK）股权激励 233 股**，受政策限制**只能卖不能买**，目标之一是找合适的卖出时机
- 解释要求：
  - 专业术语第一次出现时用一句话解释清楚
  - 指出问题时必须说明**为什么**，不只说"是什么"——用户在学习，不是只要答案
  - 代码注释写得教学化一些
- ⭐ **用户是决策者**（2026-08-14 红利暂停事件教训）：用户提出的任何偏离计划的诉求，
  先给出数据影响（如"计划 26 实测：红利权重 0~25% 年化仅差 0.3pp"），然后**尊重决定**
  并帮其落成有规则的方案——不劝、不压、不用文档压人。纪律是用户的工具，不是用户的枷锁；
  引用文档/纪律时先核对原文，不许自己发挥（教训：把"学费=心理成本"发挥成"应该为纪律亏钱"）。

## 项目目标
学习并验证量化策略，最终服务两个真实需求：
1. **基金量化**：为支付宝场外基金（指数基金 / ETF联接 / QDII）设计**低频**策略并回测验证
2. **腾讯卖出时机**：为 233 股腾讯（00700.HK）设计规则化的卖出分析框架

学习链路（前期用 A股个股/指数练手——数据规范、规则简单；方法成熟后迁移到基金和港股）：
```
获取历史数据 → 编写策略（明确的买卖规则）→ 回测模拟 → 与基准对比评估
```

## ⭐ 核心工作规则（每次写代码必须执行）
1. **写完任何策略或回测代码后，主动对照 [Knowledge/backtest_checklist.md](Knowledge/backtest_checklist.md) 逐项自检**，并在回复中明确告诉用户：检查了哪些项、发现了什么问题。用户最担心的是：**未来函数（用未来数据抄答案）**和**过拟合**。
2. 实现技术指标前，公式对照 [Knowledge/technical_indicators.md](Knowledge/technical_indicators.md)；实现与标准定义有出入时主动提醒。
3. 计算绩效指标（年化、回撤、夏普等）时，口径以 [Knowledge/metrics.md](Knowledge/metrics.md) 为准。
4. 涉及数据源、复权、T+1、涨跌停等交易规则时，参考 [Knowledge/data_sources.md](Knowledge/data_sources.md)。
5. 设计任何**卖出/离场规则**（止盈、止损、移动止盈）时，参考 [Knowledge/exit_rules.md](Knowledge/exit_rules.md)——里面有真实数据模拟结论和纪律模板。
6. **回测一律走框架，不要在分析脚本里另写循环**：单标的用 `quant/engine.py`（策略给
   入场/离场两个判断）；多标的组合用 `quant/portfolio.py`（策略给一个决策函数
   `decide_fn(ctx) -> {标的: 带符号金额}`，正=买入金额、负=卖出金额，见 [quant/rebalance.py](quant/rebalance.py)）。
7. **用户丢来一篇网文策略（知乎/公众号）时，按 [Knowledge/strategy_translation.md](Knowledge/strategy_translation.md)
   的流程走**：产出物只有一个策略文件 + 注册两行，run.py 改一行名字就能跑；
   规则歧义显式披露、参数照抄原文不许"顺手调好"；确实塞不进框架的（盘中触价/横截面选股/
   非日频）先说明原因再另写 analysis 脚本。

## 文档维护规则
- **计划管理**：每个开发任务在 [plans/](plans/) 建计划文件并登记索引；进度只改 plans，不改本文件
- **轮子沉淀**：代码被 2 个及以上场景用到、或用户说"这个可以当轮子"时，收录进 [wheels.md](wheels.md)（含功能/签名/代码/示例/校验状态）
- **知识沉淀**：用户学到的新概念、踩过的坑，整理进 `Knowledge/` 对应文件（没有合适的就新建），让知识库持续生长
- 目录结构变化时，同步更新本文件

## 计划与进度管理
- 开发计划全部放在 [plans/](plans/) 目录；**当前状态以 [plans/README.md](plans/README.md) 索引为唯一事实来源**
- 开始任何新任务前：先查 plans/README.md；新任务要新建计划文件（命名 `NN-名称.md`）并登记索引
- 任务完成时：更新计划状态和完成日期；执行中踩的坑，有价值的转入 Knowledge/
- 本文件**不记录具体进度**，只保留稳定信息

## 用户已完成的基础（稳定信息）
- pandas / numpy / matplotlib 基础，mplfinance 画 K 线（练习在 lianghuaLearn.py）
- 手写 MACD、KDJ 指标（已收录 wheels.md，公式已校验 ✓）

## 技术栈与约定
- Python 3 + pandas / numpy / matplotlib / mplfinance；akshare 1.18（已安装）
- `lianghuaLearn.py` 是课程练习文件，**保持原样不要重构**；新功能开新文件
  （唯一例外：2026-07-25 demo.csv 移入 data/，只同步了 6 处路径字符串，逻辑一行未动）
- 数据统一存 `data/` 目录（CSV 缓存），列名统一：`date, open, high, low, close, volume`
- 快速查行情（含"现在腾讯多少钱"这类问题）：**先跑 `python quote.py <名称或代码>`**，别手写临时查询代码
- 问"某只基金能不能买 / 限购多少"：**先跑 `python fund_limit.py <关键词>`**（QDII 限额天天变，别引用文档里的旧数字）
- 写代码取数一律走 [fetch_data.py](fetch_data.py) 的轮子（`fetch_daily` / `fetch_fund_nav` / `fetch_spot_bar`），不要散落地直接调 akshare/requests

## 目录结构
```
lianghuaLearn/
├── CLAUDE.md                     ← 本文件
├── wheels.md                     ← 可复用轮子库
├── plans/                        ← 开发计划（索引见 plans/README.md）
├── Knowledge/                    ← 知识库（校验代码正确性的依据）
│   ├── README.md                 ← 索引
│   ├── backtest_checklist.md     ← 回测自检清单（防未来函数/过拟合等）
│   ├── technical_indicators.md   ← 技术指标标准公式
│   ├── data_sources.md           ← 数据源与交易规则（含双源容灾约定）
│   ├── funds.md                  ← 场外基金规则（支付宝渠道必读）
│   ├── exit_rules.md             ← 离场规则（止盈/移动止盈，含真实模拟结论）
│   ├── metrics.md                ← 绩效指标标准算法
│   ├── volume_price.md           ← 量价关系经典框架 + 现实校准（口诀须回测验证）
│   ├── timing_signals.md         ← 择时信号总览：趋势/均值回复两派 + 本项目实测汇总
│   ├── stock_selection.md        ← 选股原则三派 + 负面清单 + "指数=公开选股规则"
│   ├── wave_gann.md              ← 波浪/江恩速览 + 为何无法机械回测（不可证伪）
│   ├── bull_bear_balance.md      ← 多空力量流派：资金流/筹码/广度/订单流（全是代理指标）
│   ├── strategy_fit.md           ← 策略×标的人格匹配矩阵（选策略前必读）
│   ├── strategy_translation.md   ← ⭐ 网文 → 策略文件的固定流程（拿到知乎文先看这个）
│   └── zhihu/                    ← 网文原文 + 落成物对照表（zhihu/README.md：文章↔策略文件↔能否实盘）
├── run.py                        ← ⭐ 回测实验台：日常唯一要改的文件
│                                    单标的模式：改标的+策略名两行（文字报告+买卖点图）
│                                    组合模式：策略名写组合名即自动切换（plans/17）
│                                    两种模式写名单都进比选模式
├── quant/                        ← 回测框架包（plans/07，分层：数据→指标→策略→引擎→评估）
│   ├── data.py                   ← ① 取数契约（缓存→自动下载+体检；基金净值模式）
│   ├── indicators.py             ← ② 指标纯函数（MA/RSI/BIAS/MACD/KDJ/BOLL）
│   ├── signals.py                ← ③ 入场信号库（6 个超跌信号 + cross_down）
│   ├── exits.py                  ← ③ 离场：ExitSpec 参数工厂 + exit_below_ma/exit_trailing
│   ├── rebalance.py               ← ③ 组合决策函数工厂（阈值再平衡/买入持有/定期再平衡）
│   ├── grid.py                    ← ③ 网格决策函数工厂（日频近似版，plans/19；盘中口径见 analysis/analyze_grid_etf.py）
│   ├── adapter.py                 ← ③ 择时策略 → 组合决策函数适配器（plans/20：规则只有一份，能同图比净值）
│   ├── engine.py                 ← ④ 事件循环（T+1 次日成交）+ assert_no_lookahead 门禁
│   ├── portfolio.py              ← ④ 组合引擎（plans/17：decide_fn(ctx)→每只买卖金额，T+1 成交；
│   │                                 plans/23：逐日分腿记损益，改仓即写"上一段各腿赚亏"进成交日志）
│   ├── portfolio_data.py         ← ④ 组合取数/日期对齐/PortfolioContext 今日快照
│   ├── portfolio_fill.py         ← ④ 组合订单撮合（先卖后买/不透支不卖空/双边成本）
│   ├── metrics.py / report.py    ← ⑤ 绩效计算 / 报告（对比表/参数扰动/样本量警报）
│   ├── attribution.py            ← ⑤ 收益归因计算（plans/23：钱是哪条腿赚的，金额法+守恒断言）
│   ├── report_attribution.py     ← ⑤ 归因报告（总账表默认进每次组合回测 + 分段明细打印）
│   ├── report_portfolio.py       ← ⑤ 组合报告总装（本策略 vs 不再平衡对照 vs 基准 + 阈值敏感性 + 归因）
│   ├── report_portfolio_parts.py ← ⑤ 组合报告零件（绩效行/成交明细/权重漂移/敏感性扫描）
│   ├── plot.py                   ← ⑤ 买卖点标注图（run.py 每次回测自动产出 PNG）
│   ├── plot_compare.py           ← ⑤ 策略比选图（STRATEGY 给名单时：n 价格子图 + 共享净值图）
│   ├── plot_attribution.py       ← ⑤ 归因图零件（各成分累计贡献曲线，含合计对账线）
│   ├── plot_portfolio.py         ← ⑤ 组合图（净值/权重漂移+调仓点/各腿累计贡献/再平衡净贡献 + 比选图）
│   ├── strategies/               ← ③ 单标的策略库：一套打法一个文件 + __init__.py 注册表
│   └── portfolios/               ← ③ 组合配方库：一个配方一个文件 + __init__.py 注册表
├── test_framework.py             ← 框架主测试：v3 逐笔回归 + 因果门禁 + 数据契约（全绿才算可信）
├── test_portfolio.py             ← 组合引擎测试（plans/17：账目/T+1/成本/不透支不卖空/注册表
│                                    + plans/23：分腿归因守恒，共 10 项）
├── archive/                      ← 冻结的历史实验脚本（知乎 v1~v4，一行不改，见 archive/README.md）
├── fetch_data.py                 ← 数据获取轮子（股票双源容灾 + 基金净值 + 港股当日快照
│                                    + 基金申购状态/限额 fetch_fund_purchase
│                                    + 全市场分红/融资三表 + 逐股 IPO 补全 fetch_ipo_amount，
│                                    缓存含 data/dividend_financing/）
├── quote.py                      ← 自助查询工具：名称/代码 → 最近数据 + 图（用户随手用）
├── fund_limit.py                 ← 自助查限购：关键词 → 申购状态/日限额/按公司去重的叠加上限
├── git_gui_tool.py               ← Git 弹窗小工具（tkinter，免记 git 命令）
├── plot_kline.py                 ← 读缓存 CSV 画 K 线/收盘曲线 PNG
├── analysis/                     ← 分析脚本目录：一个计划一个可重跑 analyze_*.py（见 analysis/README.md）
├── demos/                        ← 学习示例（离场规则/基金净值/腾讯周K，见 demos/README.md）
├── data/                         ← 行情/净值缓存 + 课程样例数据 demo.csv
└── lianghuaLearn.py              ← 课程练习（逻辑勿动；demo.csv 已挪入 data/，6 处路径字符串已同步）
```
