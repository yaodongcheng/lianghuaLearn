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
- Python 3 + pandas / numpy / matplotlib / mplfinance；akshare（待安装）
- `lianghuaLearn.py` 是课程练习文件，**保持原样不要重构**；新功能开新文件
- 数据统一存 `data/` 目录（CSV 缓存），列名统一：`date, open, high, low, close, volume`

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
│   ├── data_sources.md           ← 数据源与交易规则
│   ├── funds.md                  ← 场外基金规则（支付宝渠道必读）
│   └── metrics.md                ← 绩效指标标准算法
├── lianghuaLearn.py              ← 课程练习（勿动）
└── demo.csv                      ← 练习用样例数据
```
