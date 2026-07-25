# 07 回测框架抽取（quant/ 包）

> 状态：已完成 | 开始：2026-07-25 | 完成：2026-07-25

## 背景（为什么做）
知乎策略验证系列（v1~v4）产生了 4 个脚本，存在大量重复：
- `run_backtest` 有两份实现（v1 独立旧版；v2/v3 演进版）
- `cross_down`、`cal_rsi`、`cal_bias`、`metrics`/`summarize`、参数扰动循环、明细打印，各抄一份
- 数据加载 + `set_index` 每个脚本重写一遍

用户的判断（正确）：合理的量化框架 = **稳定的外围 + 可插拔的买卖函数**。

## 目标架构：分层与调用关系

**调用方向自上而下（⑥→①）。"稳定"的真正含义：下层不 import 上层——
上层怎么改，下层一行不用动。**

```
⑥ 实验层    run.py（quant/ 包外的薄胶水）：日常唯一要改的文件——
             只改两行：① 标的名称 ② 策略名（策略本体在 quant/strategies/ 管理）
             │ 调用
⑤ 评估层    report.py（打印明细/对比表/扰动表） ← metrics.py（绩效计算）
             │ 输入是④的产出
④ 引擎层    engine.py：事件循环（全项目唯一一份）——它主动调用③：每天问
             "今天买不买？"（entry_fn）、"有货，今天卖不卖？"（exit_fn）
             │ 调用
③ 策略层    signals.py 入场信号 ＋ exits.py 离场规则
             ⭐ quant/ 包内唯一的变化点——但它是"插槽"不是"地基"：
             位置由控制流决定（引擎必须调它），稳定性体现在【接口不变】：
             函数签名固定，具体策略随便换（插座 vs 电器），新增策略引擎零改动
             │ 用②算指标
② 指标层    indicators.py：RSI / BIAS / MACD / KDJ / BOLL / MA（纯函数）
             │ 读①的标准数据
① 数据层    data.py → fetch_data.py（已有轮子：双源容灾下载 + CSV 缓存）
```

| 层 | 职责 | 变化频率 | 防坑职责（见"防坑设计"节） |
|---|---|---|---|
| ① 数据 | 取数、缓存、体检、统一列名 | 不变 | 复权/来源一致性 |
| ② 指标 | 纯函数计算指标列 | 基本不变 | 公式对照 technical_indicators.md |
| ③ 策略 | 入场信号 + 离场规则 | ⭐ 每个策略不同 | 因果性测试（无未来函数） |
| ④ 引擎 | T+1 事件循环、成本、记账 | 不变 | 强制次日成交、min_hold |
| ⑤ 评估 | 绩效指标、报告 | 不变 | 口径以 metrics.md 为准 |
| ⑥ 实验 | 组装策略跑实验 | 每次都写 | 样本量/参数数警告 |

文件清单（对应上面六层）：
```
run.py                 # ⑥ 实验台：日常唯一要改的文件（只改两行，见"用户接口"节）
quant/
├── __init__.py        # run.py 只需 import 这一个包
├── data.py            # ① load_data / prepare
├── indicators.py      # ②
├── signals.py         # ③ 入场：sig_*(df, **params) -> bool Series + cross_down
├── exits.py           # ③ 离场：ExitSpec 工厂 + 现成函数 + 自定义协议
├── engine.py          # ④ run_backtest(df, entry_fn, exit_fn, ...)
├── metrics.py         # ⑤
├── report.py          # ⑤
└── strategies/        # ③ 策略库：一套打法一个文件（如 bias_oversold.py），__init__.py 登记注册表
```

## 用户接口：`run.py` 实验台 + `strategies/` 策略库

**分工**（用户 2026-07-25 确认的最终形态）：
- **策略在 `quant/strategies/` 文件夹里管理**——入场函数和离场规则写在策略文件里，
  一套打法一个文件；日常"改入场/离场" = 改对应策略文件（或新建一个）
- **`run.py` 只负责"选"**：选标的 + 选策略名，不写任何策略逻辑

### run.py：日常只改两行

```python
# run.py —— 回测实验台。日常只改下面两行，其余不用动
# ================= 只改这里 =================
TARGET   = "上证指数"          # ① 标的：指数名/股票名/基金名/代码
STRATEGY = "bias_oversold"     # ② 策略：strategies/ 里登记的名字
# （可选第三行）EXIT_OVERRIDE = ExitSpec(...)   # 临时换离场做对比实验，不动策略文件
# ============================================
```

### strategies/ 里的策略文件长什么样（完整案例）

```python
# quant/strategies/bias_oversold.py
"""策略：BIAS 超跌抄底（知乎策略验证 v3 实测综合最佳，详见 Knowledge/zhihu/吃超跌恐慌修复策略.md）"""
from quant import Strategy, ExitSpec
from quant.indicators import cal_bias
from quant.signals import cross_down

def entry(df):
    """BIAS20 ≤ -6% 首日触发（入场函数写在策略文件里，策略自带）"""
    return cross_down(cal_bias(df["close"], 20) <= -0.06)

STRATEGY = Strategy(
    name="bias_oversold",
    entry_fn=entry,
    exit=ExitSpec(take_profit=0.05, max_hold=20),
    note="上证实测：9 笔/胜率 89%/年化 4.6%/回撤 -5.3%（2018-07~2026-07）",
)
```

入场函数契约：输入标准 df（date 索引 + open/high/low/close/volume 六列），
输出与 df 等长的**布尔 Series**；只能用当天及以前的数据
（`assert_no_lookahead` 自动验证）。多策略复用的信号才放进 signals.py 信号库。

### 三种典型操作分别去哪

| 我想…… | 去哪改 | 改动量 |
|---|---|---|
| 换个标的/换个策略跑 | `run.py` 两行 | 2 行 |
| 新写一个策略（入场+离场） | `strategies/` 新建文件（照上面模板）+ `strategies/__init__.py` 登记一行 | 1 文件 + 1 行 |
| 同一入场对比几种离场 | `run.py` 解开 `EXIT_OVERRIDE` 注释 | 1 行 |
| 写通用信号给多个策略复用 | `signals.py` 添加并过 `assert_no_lookahead` | 按信号复杂度 |

### ① TARGET 的合法写法（名称解析复用 quote.py 的 resolve 轮子）

| 写法 | 例子 |
|---|---|
| 指数名 | `"上证指数"` / `"沪深300"` |
| 股票名 | `"贵州茅台"` |
| 基金名 | `"永赢半导体C"` |
| 代码 | `"000300"` / `"600519"` / `"00700"` / `"025209"` |

基金自动切净值模式：`open=close=nav`（按当日净值成交）+ C 类费率 + min_hold≥5 交易日
（覆盖 7 个自然日惩罚费红线，见 funds.md）。

### 策略文件里 `entry_fn` 的三种给法

```python
entry_fn = entry                          # A：本文件自定义的函数（上面案例）
entry_fn = sig_rsi6_oversold              # B：signals.py 信号库里的复用信号
entry_fn = lambda df: sig_crash(df, n=10, threshold=-0.08)   # C：库信号调参数
```

### 策略文件里 `exit=` 的三种给法

**给法 A：ExitSpec 参数工厂**（覆盖 90% 场景）：
```python
exit = ExitSpec(take_profit=0.05, max_hold=20)                  # +5% 止盈，20 天超期
exit = ExitSpec(take_profit=0.10, stop_loss=0.05, max_hold=60)  # 加止损
exit = ExitSpec(trail_activate=0.05, trail_pct=0.03, max_hold=60)  # 移动止盈：浮盈5%后回撤3%走
exit = ExitSpec(take_profit=0.05, max_hold=20, min_hold=5)      # 基金：最少拿5天再允许卖
```

**给法 B：现成函数**（exits.py 内置）：
```python
exit = exit_below_ma(20)     # 收盘跌破 MA20 离场
exit = exit_trailing(0.10)   # 从持仓最高收盘回撤 10% 离场
```

**给法 C：完全自定义函数**——完整例子（组合逻辑，工厂表达不了的）：
```python
def exit_ma20_or_timeout(position, row, hist):
    """跌破 MA20 离场；但买入未满 5 天不卖；最多拿 30 天。
    position：entry_price / entry_date / hold_days / peak_close（引擎维护）
    row：当日 open/close
    hist：截至当日的历史切片——物理上不含未来数据"""
    if position.hold_days >= 30:
        return "超期"
    if position.hold_days < 5:
        return None                       # 未满 5 天，什么也不做
    ma20 = hist["close"].rolling(20).mean().iloc[-1]
    if row["close"] < ma20:
        return "跌破MA20"
    return None

exit = exit_ma20_or_timeout   # 给函数本身，不加括号
```

### 配套机制
- 报告开头**回显三要素**（标的/策略名/离场参数）——每张报告自带"实验条件"，防混淆
- 可选 CLI 覆盖：`python run.py 茅台 --strategy bias_oversold`
- 策略文件的 `note` 字段记录实测表现/来源——`strategies/` 同时是策略档案库

## ① 数据层契约（回应批评 2：本地可能没有数据）

`load_data(code)` 的明确行为，实验脚本永远不需要关心数据从哪来：
1. 缓存新鲜 → 读缓存，打印 `✓ 缓存 data/idx_000001_raw.csv（2076 行，2018-01-02 ~ 2026-07-24）`
2. 缓存缺失或过期 → **自动走 fetch_daily 双源下载**（东财优先、新浪兜底，已有轮子）
   → 下载后自动 `check_daily` 体检 → 打印来源、行数、区间
3. 失败 → 明确报错（不静默返回空表）
4. 另提供 `prepare([codes])`：实验前批量预下载，避免跑到一半断网

## ③ 离场层设计（回应批评 3：第一天就开放自定义函数）

**引擎只认一种东西——离场函数：**
```python
def exit_fn(position, row, hist) -> str | None
# position：entry_price / entry_date / hold_days / peak_close（引擎维护）
# row：当日 open/close
# hist：截至当日的历史切片 df.iloc[:i+1]——引擎只传切片，
#        自定义函数【物理上拿不到】未来数据（契约级防未来函数）
# 返回离场原因字符串（"止损"/"跌破MA20"…）或 None（不离场）
```

exits.py 提供三档，由易到难：
1. **参数工厂**：`ExitSpec(take_profit=0.05, stop_loss=None, max_hold=20,
   trail_activate=None, trail_pct=None, min_hold=0).to_fn()` —— 覆盖现有全部实验
2. **现成指标离场**：`exit_below_ma(n=20)`（跌破 MA20 离场）、`exit_trailing(pct=0.10)` 等
3. **完全自定义**：按上面签名写函数即可，≤5 行

入场信号同理：`entry_fn(df) -> bool Series`，约定因果性（见防坑设计的自动测试）。

## 框架级防坑设计（回应批评 4：把 checklist 变成机制，不靠自觉）

| checklist 坑 | 框架机制 |
|---|---|
| **未来函数** | ① 引擎强制 T 日信号 → T+1 开盘成交，无可选项；② 自定义离场函数只收到 `hist` 历史切片；③ ⭐ 内置 `assert_no_lookahead(entry_fn, df)` **前缀不变性测试**：把 df 截断到第 k 天重算信号，与全量计算的前 k 项必须逐日一致——`shift(-1)`、全样本归一化这类 bug 一测就现形，作为 signals.py 每个新信号的强制门禁 |
| **过拟合** | ① report.py 内置 `param_sweep`（参数扰动表一键出）；② `run_experiment` 自动警告：参数 >4 个、交易 <30 笔时打印"样本量/参数数警报"；③ 提供 `split_sample(df, 切点)` 样本内/外切分工具 |
| **成本** | 引擎 cost 参数默认 0.001；预留基金费率模式（持有 <min_hold 天禁卖 + 惩罚费 1.5%），计划 04 基金策略直接启用 |
| **T+1 / 涨跌停** | T+1 引擎内置；涨跌停暂标注（指数/ETF 策略），个股策略报告自动附注 |
| **绩效口径** | metrics.py 每个函数注释引用 metrics.md 对应条目 |

## 明确不做（防过度设计）
- ❌ 多标的组合回测 / 仓位分配——当前全部策略是单标的全仓进出；接口预留，计划 04 真需要时再扩
- ❌ 引入 backtrader 等外部框架——自己这几百行是理解回测原理的最好教材
- ❌ 分钟级数据

## 设计决策（默认值，可改）
1. 包名 `quant/`（备选 `framework/`）
2. 旧脚本**不做薄化迁移、不写桥接层**（用户 2026-07-25 指示：项目刚起步，代码干净优先）：
   一次性回归验证后，v1~v4 实验脚本**原样移入 `archive/` 冻结**（一行不改），文档引用同步改路径。
   回归所需的"原版引擎"就是归档文件本身——原封不动比改写过的"薄化版"更可信
3. 回归基准以 v3 输出为准（v2 缺预热段是已知差异，v3 已修，以 v3 为正确基准）
4. **干净优先总则**：不留兼容层/桥接代码；需要改历史引用就直接改文档链接
   （项目刚起步、没有外部用户，改得起）。模块 <150 行只是上限，目标是"能一眼看懂"
5. **策略组织：函数签名协议 + Strategy dataclass 注册表，不用基类继承**（用户提议过基类方案，2026-07-25 讨论后否决）：
   - 契约是**签名**（`entry_fn(df)->bool Series` / `exit_fn(position,row,hist)->str|None`），
     策略不 import 引擎任何东西 → 解耦最彻底（基类会让所有策略反向依赖引擎）
   - 策略间共享的代码是**指标**（② indicators.py）——复用靠模块，不靠父类（组合优于继承）
   - `strategies/` 一套打法一个文件，每个文件导出 `STRATEGY = Strategy(name=..., entry_fn=..., exit=..., note=...)`
     （dataclass 只是登记元数据的"名片"，**不是基类**）；`strategies/__init__.py` 逐个登记成注册表，
     run.py 按 `name` 取用，用于注册、遍历、对比实验
   - 升级路径：将来策略需要跨日内部状态（网格/分批建仓）时，再用**实现同样签名的类**
     （约定优于继承），引擎依然零改动——到那时重新评估

## 验收标准
- [ ] 新入场信号（如"MA5 上穿 MA20"）从写函数到完整报告 ≤10 行；
      新离场规则（如"跌破 MA20"）≤5 行——两条都拿真实例子演示
- [ ] **回归一致性**：v3 的 6 信号 × 2 指数 × 4 离场，框架输出与原脚本逐笔交易一致
- [ ] 6 个超跌信号全部通过 `assert_no_lookahead`；故意写一个含 `shift(-1)` 的坏信号，
      验证测试能抓住它（负例测试）
- [ ] 断网/无缓存场景：`prepare` + `load_data` 行为符合契约（用新代码模拟测试）
- [ ] 个股数据（茅台 qfq）直接喂同一引擎
- [ ] quant/ 每模块 <150 行、教学注释；wheels.md 轮子指向 quant/
- [ ] 框架本身对照 backtest_checklist.md 逐项自检
- [ ] ⭐ **主测试用例通过**（见下节）

## ⭐ 主测试用例（用户指定：通了才算框架可复用）

**用框架重跑 [Knowledge/zhihu/吃超跌恐慌修复策略.md](../Knowledge/zhihu/吃超跌恐慌修复策略.md)
里的上证指数策略，输出必须与文档中的 v3 实测结果完全一致。**

具体判定：
1. **逐笔一致**：6 个超跌信号 × 上证指数，框架输出的每笔交易（买入日/卖出日/持有天数/收益率/
   卖出原因）与归档的原版 v3 引擎（archive/zhihu_strategy1_oversold_v3.py）**完全相同**——
   用自动化回归脚本对比，不允许"差不多"
2. **指标一致**：文档 v3 表格中的关键数字原样复现，例如：
   - 上证 BIAS20≤-6%：9 笔 / 胜率 89% / 年化 4.6% / 最大回撤 -5.3%
   - 上证 10日跌≥7%：10 笔 / 胜率 90% / 年化 4.0% / 最大回撤 -5.2%
   - 固定止盈 vs 移动止盈对比表（A/B/C/D 四档离场）同口径复现
3. **入口一致**：从 run.py 实验台出发，只改两行（TARGET="上证指数"、STRATEGY="bias_oversold"）就能跑出上述报告
4. 沪深300 同套回归作为附带验证

**推论**：主测试用例通过 = 引擎/信号/离场/数据/评估五层全部可信 →
其他策略（新信号、新离场、新标的）可放心复用框架。

## 步骤
1. engine.py：exit_fn 协议 + hist 切片机制 + min_hold + assert_no_lookahead 工具
2. data.py（契约实现）→ indicators.py → metrics.py → report.py
3. exits.py（工厂 + exit_below_ma + exit_trailing）+ signals.py（收编 6 信号，全部过因果测试）
4. strategies/ 策略库（6 个超跌信号各成一个策略文件 + __init__.py 注册表）+ run.py
5. **主测试用例**：回归脚本（框架 vs 归档 v3 引擎逐笔对比）+ run.py 复现文档 v3 数字
6. 归档：v1~v4 移入 archive/，更新全部文档引用（策略文档 / plans/06 / CLAUDE.md / wheels.md）
7. 验收标准其余逐条验证（含负例测试、无缓存场景、个股数据）
8. 文档与自检：wheels.md 轮子指向 quant/；框架对照 checklist 逐项过；本文件坑与笔记

## 坑与笔记（2026-07-25 执行记录）

**验收结果**（`python test_framework.py` 全绿）：
- ⭐ 主测试用例通过：6 信号 × 2 指数 ×（Part1 1 离场 + Part2 4 离场）共 28 组逐笔回归，
  与归档 v3 引擎完全一致（买入日/卖出日/持有天数/卖出原因/收益率 1e-12 级 + 净值曲线）
- 文档数字原样复现：上证 BIAS 9 笔/89%/4.6%/-5.3%、10日跌 10 笔/90%/4.0%/-5.2%
- 负例测试：`shift(-1)` 坏信号被 assert_no_lookahead 当场抓住
- 数据契约：中证500 无缓存自动下载+体检 ✓；乱名明确报错 ✓；prepare ✓
- 茅台 qfq 喂同一引擎 ✓；基金净值模式（open=close=累计净值）+ min_hold≥5 防线 ✓
- 模块行数：最大 engine.py 135 行，全部 <150

**执行中踩的坑**：
1. **测试脚本自己的 bug（教训：测试也要被检查）**：test_regression 用 `return df`
   返回循环变量，拿到的是最后一轮的沪深300 而不是上证——文档数字对不上时
   先怀疑了框架，实际是测试取错数据。循环变量出循环即失效，要显式按名字收集。
2. **quote.resolve 不认指数数字代码**（"000300" 会被当成股票/基金解析）：
   data.py 补了一张 INDEX_CODES 表做前置识别，故意不收 000001（股票/基金/指数三方撞码）。
3. **v4 归档后的 import 问题**：v4 写的是 `from zhihu_strategy1_oversold_v3 import ...`
   （同目录脚本式 import），归档后 `python -m archive.v4` 会失败。按"一行不改"原则
   没动它，archive/README.md 里写明了重跑方法（v4 不是回归基准，无影响）。
4. **年化口径 reconciled**：metrics.md 原文 252 交易日口径，v1~v4 实际用日历年化
   （8 年差 ~0.2pp，噪声级）。统一为日历年化并回填 metrics.md 说明，保持跨报告可比。

**框架对照 backtest_checklist.md 逐项自检**：
| 清单项 | 框架机制 | 状态 |
|---|---|---|
| 1. 未来函数 | 引擎强制 T+1 开盘成交无可选项；exit_fn 只收 hist 切片；assert_no_lookahead 门禁（6 信号过 + 负例被抓） | ✅ |
| 2. 过拟合 | report.param_sweep 扰动表；sample_warnings（>4 参数 / <30 笔自动警报，run.py 已演示触发）；split_sample 样本内外切分 | ✅ |
| 3. 成本 | cost 双边默认 0.001 买卖各扣一次；基金 min_hold≥5 自动提（run_experiment） | ✅ |
| 4. 复权 | data 层走 fetch_data 约定（个股 qfq / 指数 raw），茅台 qfq 测试通过 | ✅ |
| 5. T+1 | 买入当日收盘决策、次日开盘才成交（引擎语义，与 v3 回归一致） | ✅ |
| 6. 涨跌停 | 未建模（指数/ETF 策略影响小）；个股策略报告自动附注提醒 | ⚠️ 已标注 |
| 7. 幸存者偏差 | 单标的/指数策略不适用；全市场选股时再正视 | ✅ 不适用 |
| 8. 其他 | 停牌日数据里不存在自然跳过；100 股整手未建模（全仓学习模型，影响 <0.1%） | ⚠️ 已标注 |

**遗留说明**：
- 基金 1.5% 惩罚费未直接建模，用 min_hold≥5（≥7 自然日）规避——比建模费率更简单且不会错
- compare_table / param_sweep 是给后续实验用的，本次未在主测试里演示（v2 扰动实验已验证过方法论）
