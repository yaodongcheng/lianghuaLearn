# 网文策略 → 可跑策略文件（翻译流程）

> 用途：以后拿到任意一篇知乎/公众号策略文，按这个流程走，产出物**只有一个策略文件**
> （`quant/strategies/*.py` 或 `quant/portfolios/*.py`）+ 注册表两行，
> 然后 `run.py` 改一行名字就能跑，不再写第二套回测代码。
> 来源：plans/06 / 16 / 17 三次验网文的经验固化。

## 第 0 步：判断该走哪套契约（决策树）

```
这篇文章在讲什么？
├─ 一只标的、什么时候满仓进、什么时候清仓出（择时）
│     → quant/strategies/  契约：entry_fn(df)->bool序列 + exit_fn(...)->原因|None
├─ 几只标的、钱怎么分、什么时候重新分（配置：再平衡/股债/定投/分批建仓）
│     → quant/portfolios/   契约：decide_fn(ctx)->{标的: 带符号金额}（正买负卖）
└─ 都不像 → 见文末「落不进框架的三类」，先说清楚再动手
```

判据不是"标的有几个"，而是**决策的输出形状**：布尔（进/出）还是金额（每只买卖多少）。
仓位要分批的单标的策略（定投、金字塔加仓）也走 `portfolios/`——只放一只标的即可，
因为组合引擎允许任意金额、允许留现金，而单标的引擎只有满仓/空仓两态。

**例外一条（plans/20）**：已经写好的**择时策略要和某个组合对比**时，
**不要重新写一份组合配方**（等于把规则抄第二遍，两份实现迟早漂移），
用适配器 `quant/adapter.py` 的 `strategy_as_portfolio("策略名")` 包一层——
规则仍只有 `quant/strategies/` 那一份，配方文件只写标的和 `decide_fn=` 一行。
样例：[quant/portfolios/bottom_reversal_fund.py](../quant/portfolios/bottom_reversal_fund.py)。

## 第 1 步：把口述规则翻译成机械规则（最容易翻车的一步）

原文一律是模糊口语，必须逐条改写成"当天收盘后能唯一算出答案"的判断：

| 原文口语 | 机械化 | 要点 |
|---|---|---|
| "跌得多了就买" | 收盘 ≤ 20日均线 × (1−8%) 首日 | 首日触发（`cross_down`），否则天天发信号 |
| "涨上来就卖一点" | 相对成本 +15% 卖 1/3 | "一点"要给数字，否则不可回测 |
| "跌到低位启动网格" | 收盘 ≤ 70% × 滚动 3 年最高 | 窗口长度必须写死 |
| "占比差太多就平衡" | max(权重)−min(权重) ≥ 3% | 阈值口径：极差？偏离目标？写清楚 |

**歧义必须显式披露而不是替作者拍板**：翻译时凡是有两种读法的，在文件 docstring 里
写"原文歧义 + 本实现的选择"。真实例子：网格文作者自述在前高 76% 处启动，
违反他自己写的 70% 规则——按规则执行会早 14 个月开仓，结论差别很大（plans/16）。

## 第 2 步：参数一律照抄原文，禁止"顺手调好一点"

原文给 3% 就写 3%，给 250 日就写 250 日。**想知道参数好不好，靠第 5 步的敏感性扫描，
不靠试出一个漂亮数字**——试出来的漂亮数字就是过拟合。

## 第 3 步：写策略文件（两个模板，抄就行）

单标的（照 `quant/strategies/trend_ma250.py`）：

```python
from quant import Strategy
from quant.exits import exit_below_ma          # 或 ExitSpec(take_profit=..., max_hold=...)
from quant.indicators import cal_ma
from quant.signals import cross_down

def entry(df):                                  # df 只含截至当日数据，物理防未来函数
    return cross_down(df["close"] > cal_ma(df["close"], 250))

STRATEGY = Strategy(name="trend_ma250", entry_fn=entry, exit=exit_below_ma(250),
                    note="原文出处 + 实测数字 + 适用标的类型")
```

组合（照 `quant/portfolios/longterm_balance.py`）：

```python
from quant import Portfolio
from quant.rebalance import threshold_rebalance   # 现成工厂不够用就自己写 decide(ctx)

PORTFOLIO = Portfolio(
    name="longterm_balance",
    holdings={"纳指": "fund:270042", "黄金": "fund:000216"},   # 查询串同 load_data
    decide_fn=threshold_rebalance(weights=None, threshold=0.03),
    data_start="20130101",
    note="原文声称的数字 + 本回测实测 + 与原文的口径差异")
```

自定义决策函数的可用信息全在 `ctx`：`date/prices/hist/shares/cash/values/total/weights/
invested` + `orders_for_weights(目标权重)`。`ctx.hist` 只切到今天，**拿不到未来数据**。

文件 docstring 固定四段：原文规则原样 / 机械化后的规则 / 与原文的口径差异（标的替换、
费率、数据源）/ 教学要点。策略名用英文小写下划线，且不能与另一个注册表撞名。

## 第 4 步：注册两行

`quant/strategies/__init__.py`（或 `portfolios/__init__.py`）加 import + 进 `_ALL` 名单。

## 第 5 步：验收（不做这步不算验完，别急着相信结果）

1. `python run.py`（改 `STRATEGY` 一行）→ 文字报告 + 买卖点图/组合三联图
2. 对照 [backtest_checklist.md](backtest_checklist.md) 逐项自检，重点：未来函数、过拟合
3. 参数敏感性：单标的用 `quant.report.param_sweep`，组合报告自带阈值扫描；
   结论随参数剧烈变化 = 原文那个参数是调出来的
4. 与原文声称的数字对比：吻合 → 作者可信；差很远 → 先查自己的口径，再质疑作者
5. 可执行性收口（本项目特有）：**能不能在支付宝场外基金上做？** 需要场内条件单、
   T+0、20 只个股等权的策略，回测再漂亮也落不了地，必须在结论里写明

## 第 6 步：沉淀

原文存 `Knowledge/zhihu/`；验证过程与结论写进 `plans/NN-*.md` 并登记 plans/README.md；
新学到的坑进 `Knowledge/` 对应文件。策略文件的 `note` 写上实测数字——
下次 run.py 打报告时会回显，等于策略自带体检报告。

## 落不进框架的三类（诚实边界，别硬塞）

| 类型 | 为什么塞不进 | 现在怎么办 |
|---|---|---|
| 盘中触价成交（网格、条件单、日内止损） | 两个引擎都是"T 日决策 → T+1 收盘/净值成交"，无法在当天某个价位成交 | **写日频近似版进框架**（`quant/grid.py` + 配方 `grid_3tier`：档位按收盘价判断、次日收盘成交），把盘中版脚本留作口径对照——两版差额就是"盘中限价单"值多少钱 |
| 横截面选股（每期换一批股票） | `holdings` 是固定名单，`decide_fn` 不能凭空增删标的 | **冻结名单配方**：脚本按 point-in-time 数据选名单 → 名单写死进一个配方文件（先例：`analyze_dividend_financing.py` → `dividend_ratio_top20`），文件里注明选股日、可复现命令、幸存者偏差 |
| 非日频 / 衍生品（分钟级、期权、杠杆） | 数据层只做日频价格；无保证金、无到期日概念 | 目前不做，直接告诉用户超出框架能力 |

⭐ 2026-07-28（plans/19）实测这两个办法都成立，且**近似版的结论和精确版一致**：

| 策略 | 框架日频版 | 单独脚本（原口径） | 说明 |
|---|---|---|---|
| 网格 grid_3tier | 15769 元 / +7.19% / -20.9% / 44 笔 | 15343 元 / +6.75% / -20.6% / 62 笔（盘中触价） | 日频版反而略高 → 这个标的上"盘中挂限价单"没赚到钱，省下的 18 笔手续费更值 |
| 分红融资比 top20 | 19878 元 / +9.54% / -21.8% | 19878 元 / +9.54% / -21.8% | 完全一致（脚本本来就调框架，只是名单来源不同） |

教学要点：**近似不等于将就**。判断一个近似能不能用，办法是"两种成交模型都跑一遍，看结论
是否改变方向"——数字略有差异但排序/结论不变，说明结论不依赖那个做不到的细节，可以放心
用框架版做日常实验；若差异大到反转结论，那才必须承认框架不适用。

前两类若反复出现，正确做法是**升级引擎能力**（分批成交模型 / 动态成分），
而不是每篇文章都新写一个脚本——脚本一多，纪律就散了（plans/17 的教训）。
第一类的"日频近似"已经把网格拉回框架内（plans/19），真正的盘中成交模型待有需要再做。
