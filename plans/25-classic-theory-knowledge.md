# 25 课程经典理论知识沉淀（指标/选股/择时/波浪/江恩）

- **状态**：已完成
- **创建**：2026-07-28
- **完成**：2026-07-28

## 背景

用户之前学过技术分析与新手量化课程（指标、选股原则、择时买卖信号、波浪理论、
江恩理论），现在有点忘了，且课程缺少实际数据回测。目标：把这套知识沉淀进
`Knowledge/`，写法对标 [volume_price.md](../Knowledge/volume_price.md)——
**经典框架 + 现实校准 + 渠道适用性 + 验证路线 + 常见坑**，每条规则都标注
"本项目能不能回测、怎么回测、有没有已实测的结论"。

## 范围与分工

| 课程主题 | 落点 | 说明 |
|---|---|---|
| 指标（MACD/KDJ/MA/RSI/BOLL/BIAS） | 已有 [technical_indicators.md](../Knowledge/technical_indicators.md) | 不重复写，新文件只做引用 |
| 择时买卖信号 | `Knowledge/timing_signals.md`（新建） | 汇总本项目已有实测：plans/02 MACD、zhihu 超跌六信号横测、plans/15 年线过滤 |
| 选股原则 | `Knowledge/stock_selection.md`（新建） | 明说横截面选股框架不支持；重点转化："指数=一套公开的选股规则" |
| 波浪理论 + 江恩理论 | `Knowledge/wave_gann.md`（新建） | 内容速览 + 为什么无法机械回测 + 可提炼的可检验成分 |

## 验收标准

- [x] 三个新知识文件，风格与 volume_price.md 一致（含渠道适用性、验证路线、常见坑）
- [x] 引用的项目实测结论（plans/02、zhihu 案例、plans/15 等）数字准确
- [x] Knowledge/README.md、plans/README.md、CLAUDE.md 目录三处索引同步

## 明确不做

- 本计划**不跑新回测**。"斐波那契回撤位支撑有效性验证"等实验如要做，另立计划。
- 不补写指标公式（technical_indicators.md 已覆盖且全部校验通过）。

## 坑与笔记

- 指标部分没重写：[technical_indicators.md](../Knowledge/technical_indicators.md) 已覆盖且全部
  校验通过，新文件只做引用——避免同一知识两处维护。
- 波浪/江恩的处理定位：不是"教用户数浪"，而是"速览内容 + 解释为什么量化无法用它 +
  提炼可检验成分"。核心论点：**能被证明错是规则的优点**（金叉死叉能被回测打脸，数浪不能）。
- 后续候选（另立计划）：斐波那契回撤位/50% 回调的支撑有效性统计（analysis 脚本，非框架策略）；
  选股若要回测需 Point-in-Time 数据源，暂不做。
