# 知识库索引

这个文件夹存放量化交易各方面的参考知识，**用途是校验代码的正确性**——写完策略/回测代码后，对照这里的标准检查有没有踩坑。

| 文件 | 内容 | 什么时候用 |
|---|---|---|
| [backtest_checklist.md](backtest_checklist.md) | 回测自检清单：未来函数、过拟合、交易成本、T+1、涨跌停、复权、幸存者偏差 | ⭐ 每次写完策略/回测代码后逐项对照 |
| [technical_indicators.md](technical_indicators.md) | MACD、KDJ、MA、RSI、BOLL 等指标的标准公式与常见用法 | 实现或修改任何指标之前 |
| [data_sources.md](data_sources.md) | akshare 数据接口、复权概念、A股/港股交易规则 | 获取数据、处理数据时 |
| [funds.md](funds.md) | 场外基金（支付宝渠道）交易规则、费用、对策略设计的影响 | ⭐ 做任何基金相关策略前必读 |
| [metrics.md](metrics.md) | 年化收益、最大回撤、夏普比率等绩效指标的标准算法与"什么算好"的直觉参考 | 评估回测结果时 |

## 维护约定
- 学到新概念 → 加到对应文件，或新建主题文件并更新本索引
- 踩过的坑 → 记入 backtest_checklist.md（这是最有价值的积累）
- 发现某个文件内容有误 → 直接修正并注明
