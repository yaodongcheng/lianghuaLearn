# 轮子库（可复用代码）

> 收录标准：在 2 个及以上场景用到、且经过正确性校验的代码。
> 每个轮子包含：**功能 / 函数签名 / 代码 / 用法示例 / 校验状态与注意事项**。
> 目前阶段用文档记录；某个板块代码量变大后，再考虑抽成 `.py` 模块。

## 目录
- [数据获取](#数据获取)
  - [fetch_daily — 日线行情获取（双源容灾 + 本地缓存）](#fetch_daily--日线行情获取双源容灾--本地缓存)
  - [quote.py — 自助行情查询 CLI](#quotepy--自助行情查询-cli)
  - [fund_limit.py — 自助限购查询 CLI](#fund_limitpy--自助限购查询-cli能不能买--每天最多买多少)
- [技术指标](#技术指标)
  - [cal_macd — MACD 指标](#cal_macd--macd-指标)
  - [cal_kdj — KDJ 指标](#cal_kdj--kdj-指标)
- [回测](#回测)
  - [quant/ — 回测框架（plans/07）⭐ 新策略默认入口](#quant--回测框架plans07-交付物--新策略默认入口)
  - [quant/portfolio.py — 多标的组合再平衡引擎](#quantportfoliopy--多标的组合再平衡引擎plans16-交付物)
  - [attribution — 组合收益归因（钱是哪条腿赚的）](#attribution--组合收益归因钱是哪条腿赚的plans23)
  - [strategy_as_portfolio — 择时策略 → 组合契约适配器](#strategy_as_portfolio--择时策略--组合契约适配器plans20)
  - [cross_down — 信号首日触发](#cross_down--信号首日触发)
- [画图](#画图)
  - [A股配色 K 线样式](#a股配色-k-线样式)
  - [plot_experiment — 回测买卖点标注图](#plot_experiment--回测买卖点标注图)

---

## 数据获取

### fetch_daily — 日线行情获取（双源容灾 + 本地缓存）

**功能**：拉取 A股个股 / A股指数 / 港股个股的日线行情，统一列名后存 `data/` 缓存。
东财接口优先、新浪接口兜底（实测东财在部分企业网络被防火墙拦截，见注意事项）。

**签名**：`fetch_daily(market, symbol, start="20200101", end=None, force_refresh=False, adjust=None) -> DataFrame`

- `market`：`"a"`=A股个股 / `"idx"`=A股指数 / `"hk"`=港股个股 / `"etf"`=场内ETF
- `symbol`：`"600519"` / `"000300"` / `"00700"` / `"510210"`
- 返回列：`date, open, high, low, close, volume`，日期升序
- 复权自动约定：个股 `qfq`，指数/ETF 默认不复权；缓存文件名如 `hk_00700_qfq.csv`
- `adjust`：复权方式覆盖（2026-07-27 新增）。**ETF 回测务必 `adjust="qfq"`**——
  raw 价遇份额拆分出现假暴跌（512480 两次 1拆2，单日假跌 -48.9%/-50.7%，
  见 Knowledge/data_sources.md）。显式复权只走东财（新浪 ETF 接口无复权参数）
- 缓存最后日期距今 ≤7 天直接读缓存；`force_refresh=True` 强制重下
- 缓存尾部新鲜但起点不覆盖时（标的上市晚于请求起点），下载失败会退回用缓存
  并明确警告，不再硬报错（2026-07-27 新增 rescue 机制）

**代码**：完整实现见 [fetch_data.py](fetch_data.py)（约 180 行，含注释）。核心结构：

```python
SOURCES = [("东财", _fetch_eastmoney), ("新浪", _fetch_sina)]  # 按序尝试

def fetch_daily(market, symbol, start="20200101", end=None, force_refresh=False):
    # 1) 缓存新鲜 → 直接读 data/{market}_{symbol}_{adjust}.csv
    # 2) 否则 _fetch_with_fallback() 依次尝试各数据源（每个源重试 2 次）
    # 3) _normalize() 统一 6 列后写缓存
```

配套体检函数 `check_daily(df, name)`：打印行数/区间/缺失值/重复日期/非正价格/单日波动 Top5（抓复权缺口）。

**同文件内的相关轮子**（均 ✅ 2026-07-24 验证）：

| 函数 | 功能 | 关键注意 |
|---|---|---|
| `fetch_fund_nav(code)` | 场外基金历史净值（东财F10）→ `date, nav, acc_nav, daily_ret`，缓存 `data/fund_{code}.csv` | 当日净值晚上才公布；东财基金 F10 主机在本网络可用 |
| `fetch_spot_bar(symbol)` | 港股当日实时快照 → 1 行 6 列日 K | 日 K 线接口收盘后数小时才更新，用快照补当日；**只内存用、不写缓存**；新浪接口必须带 Referer 头 |
| `fetch_dividend_table(period)` | 全市场某报告期分红表（2000年起年报/中报）→ `code, name, div_per_10, total_shares, ex_date`，缓存 `data/dividend_financing/`（✅ 2026-07-27） | 分红总额=div_per_10/10×总股本；预案不算数——按 ex_date ≤ 选股日过滤 |
| `fetch_financing_tables()` | 全市场融资三表合一（IPO/增发/配股）→ `code, date, amount, kind, list_date`（✅ 2026-07-27） | **单位坑：IPO=万股、增发/配股=股**；IPO/增发只覆盖 2010 年起，老股需逐股补 IPO（茅台"融资=0"误杀坑，见 data_sources.md 第六节） |
| `fetch_ipo_amount(codes, as_of=None)` | 逐股补全 IPO 募资额（元）→ `(ok: {code: 金额}, failed: [code])`，缓存 `data/dividend_financing/audit_ipo.csv`（✅ 2026-07-28，458+559 只全部命中缓存跑通） | **失败绝不当 0**：静默失败=篡改（建行真 IPO 571 亿，失败时只剩配股 22 亿 → 分红融资比从 14 虚高到 359，直接窜到榜首）。逐股接口单位是**万元**；重试 3 次；仍失败的进 failed 由调用方剔除（宁缺毋假） |
| `fetch_fund_purchase(keyword)` | 全市场场外基金申购状态 + 日累计限额 → `code, name, status, min_buy, day_limit, fee`，缓存当天一份 `data/fund_purchase.csv`（✅ 2026-07-28，27060 只） | 判断"买得进去吗"用 **status**（限大额/开放申购=能买，暂停申购=买不了）；`day_limit=0` 是接口没给（多为机构份额），`day_limit ≥ 1e8` 是天文数字=不限购；额度按**基金公司**分配，同公司 A/C/D 份额共享，不能相加 |

**用法**：
```python
from fetch_data import fetch_daily, check_daily
df = fetch_daily("hk", "00700", start="20200101")   # 腾讯前复权日线
check_daily(df, "腾讯")                              # 下载后先体检再用
```

**校验状态**：✅ 已验证（2026-07-24）：腾讯 1611 行 / 茅台 1589 行 / 沪深300 1589 行，
缺失值、重复日期、非正价格均为 0；单日波动 Top5 全部对应真实事件；
前复权自洽性检查通过（qfq 最新价=市价，历史价低于不复权价）；K 线图无复权缺口。

**注意事项**：
- 东财 kline 接口用带编号的子域名（如 `33.push2his.eastmoney.com`），**部分企业网络会
  拦截这类域名**（连接被直接断开）；此时自动走新浪兜底。两源的前复权因子算法略有差异，
  **同一只票的回测不要混用来源**（一致性比来源更重要）。
- 新浪的 A 股指数代码统一用 `sh` 前缀（`sh000300`），写成 `sz000300` 会返回畸形数据。
- 新浪一次返回全部历史；东财按区间请求。**缓存只增不减**：下载后若已有旧缓存会按日期合并
  （同日期取新值），小区间请求不会破坏大区间缓存（2026-07-24 修过相关 bug：曾把 1611 行
  全量缓存覆盖成 7 行周数据——教训：缓存永远存完整区间，过滤只在返回前做）。

---

### quote.py — 自助行情查询 CLI

**功能**：名称或代码 → 自动识别市场（A股/港股/指数/基金）→ 打印最近 10 行数据 + 关键数字
（最新价/净值、近 5 日、近 20 日涨跌）+ 出图（K线或净值曲线，存 `data/quote_*.png`）。
**用户和 Claude 查询行情的唯一入口，别再手写临时查询代码。**

**用法**：
```bash
python quote.py 腾讯 | 00700 | 贵州茅台 | 600519 | 沪深300 | 025209
python quote.py                    # 不带参数 → 交互式输入
python quote.py 000001 --stock     # 代码撞车（股票和基金同码）时手动指明
python quote.py 腾讯 --refresh     # 强制重新下载（默认读缓存，秒回）
```

**能力清单**（已实现，勿重复造）：
- 名称→代码：新浪联想接口（`type=111` A股 / `31` 港股 / 基金名单东财缓存 7 天）；指数有别名表
- 港股收盘后自动补当日实时快照（日 K 线接口更新慢，见 fetch_spot_bar）
- 歧义处理：基金名称匹配多只 → 列候选；股票基金撞码 → 提示 `--stock`/`--fund`
- 输出图：股票画 60 日 K（复用 A股配色样式轮子），基金画净值曲线
- `--days N`：只看近 N 个自然日；`--bench [指数别名]`：叠加基准画**区间收益率对比图**
  （默认沪深300，可 `--bench 上证指数`；输出超额收益数字。股票加 --bench 时自动从 K 线切换为收益率曲线）

**代码内复用**：`from quote import resolve` 可把"名称/代码 → (kind, code, 名称)"的解析能力
嵌进任何脚本（比如以后批量选股时喂名称列表）。

**校验状态**：✅ 已验证（2026-07-24）：腾讯/00700/600519/沪深300/025209/名称歧义/代码撞车 7 种输入全通过。
**注意事项**：依赖 fetch_data.py 和 plot_kline.py 的轮子；基金名单缓存 `data/_fund_list.csv`（7 天自动更新）。

### fund_limit.py — 自助限购查询 CLI（能不能买 / 每天最多买多少）

**功能**：关键词 → 列出该类场外基金的**申购状态 + 每日限额**，可买的按额度排序，
并给出"按基金公司去重后的可叠加上限"。**落地任何一只基金前先跑一遍**——QDII
（纳指/标普/黄金外盘/原油）受外汇额度限制常年限购，而额度天天变，写死的数字必过期。

**用法**：
```bash
python fund_limit.py 纳斯达克100      # → 建信 539001 最高 100 元/日；11 家公司叠加 ≈ 195 元/日
python fund_limit.py 黄金             # → 30 只不限购（如 000216 华安黄金ETF联接A）
python fund_limit.py 000216 --all     # 直接查代码；--all 连"暂停申购"的一起列
```

**三个读数陷阱**（都已在输出里处理）：
1. **状态优先于额度**：暂停申购的基金那一栏还留着历史限额，看着能买其实买不了
2. **同公司份额不能相加**：外汇额度按**基金公司**分配，A/C/D 份额共享同一份额度
   → 脚本按公司取 max 再求和，不然会把 3 只建信份额算成 300 元/日
3. **天文数字 = 不限购**：接口对不限购的基金返回 1000 亿这种值，`day_limit ≥ 1e8`
   一律显示"不限"，并直接提示"有不限购的选择，不用凑额度"

**校验状态**：✅ 2026-07-28 三种输入（纳斯达克100 / 黄金 / 000216）跑通，
与东财页面口径一致；轮子是 `fetch_data.fetch_fund_purchase`。

---

## 技术指标

### cal_macd — MACD 指标

**功能**：计算 MACD 的 DIF、DEA、BAR（柱）三个值。

**签名**：`cal_macd(df, fast=12, slow=26, signal=9) -> df`

**输入约定**：`df` 需含 `end_price` 列（收盘价）。计算结果以 `dif` / `dea` / `bar` 三列就地加进 df。

```python
def cal_macd(df, fast=12, slow=26, signal=9):
    ewma12 = df['end_price'].ewm(span=fast, adjust=False).mean()
    ewma26 = df['end_price'].ewm(span=slow, adjust=False).mean()
    df['dif'] = ewma12 - ewma26
    df['dea'] = df['dif'].ewm(span=signal, adjust=False).mean()
    df['bar'] = (df['dif'] - df['dea']) * 2   # ×2 是国内行情软件口径
    return df
```

**用法**：
```python
df = cal_macd(df)
# 金叉信号：DIF 上穿 DEA
gold_cross = (df['dif'] > df['dea']) & (df['dif'].shift(1) <= df['dea'].shift(1))
```

**校验状态**：✅ 已对照 [Knowledge/technical_indicators.md](Knowledge/technical_indicators.md) 标准公式校验（2026-07-24）。
**注意事项**：
- `bar = 2×(dif-dea)` 是同花顺/通达信等国内软件口径；国外软件是 1 倍。判断金叉死叉不受影响。
- EMA 初始值取法不同会导致前几十根 K 线的数值与行情软件略有差异，属正常现象，不影响信号。

---

### cal_kdj — KDJ 指标

**功能**：计算 KDJ 的 K、D、J 三个值（9 日参数）。

**签名**：`cal_kdj(df, n=9) -> df`

**输入约定**：`df` 需含 `end_price`（收盘）、`high_price`（最高）、`low_price`（最低）三列。

```python
def cal_kdj(df, n=9):
    low_min = df['low_price'].rolling(n, min_periods=n).min()
    low_min.fillna(value=df['low_price'].expanding().min(), inplace=True)
    high_max = df['high_price'].rolling(n, min_periods=n).max()
    high_max.fillna(value=df['high_price'].expanding().max(), inplace=True)

    rsv = (df['end_price'] - low_min) / (high_max - low_min) * 100
    df['kdj_k'] = rsv.ewm(com=2).mean()        # com=2 → α=1/3，等价于国内口径 SMA(RSV,3,1)
    df['kdj_d'] = df['kdj_k'].ewm(com=2).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    return df
```

**校验状态**：✅ 已对照标准公式校验（2026-07-24）。
**注意事项**：
- 国内 KDJ 的平滑用的是 `SMA(X,3,1)`（α=1/3 的指数平滑），`ewm(com=2)` 正好等价（α = 1/(1+com)）。
- 前 n-1 日用 expanding 填充是为了让早期也有值；行情软件通常从第 9 天才开始显示，早期数值略有出入正常。

---

## 回测

### quant/ — 回测框架（plans/07 交付物）⭐ 新策略默认入口

**功能**：单标的、全仓进出、T+1 低频策略的完整回测框架。六层分层：
`data.py`（取数）→ `indicators.py`（指标）→ `signals.py`/`exits.py`（策略插槽）
→ `engine.py`（事件循环）→ `metrics.py`/`report.py`（评估）。
**下层不 import 上层；策略契约是函数签名，不是基类。**

**日常用法（run.py 实验台，只改两行）**：
```python
# run.py
TARGET   = "上证指数"       # 标的：指数名/股票名/基金名/代码
STRATEGY = "bias_oversold"  # 策略：quant/strategies/ 里登记的名字
# 然后 python run.py；或 CLI 覆盖：python run.py 贵州茅台 --strategy crash_10d
```

**代码内用法**：
```python
from quant import ExitSpec, run_backtest, assert_no_lookahead
from quant.data import load_data
from quant import signals

df, info = load_data("上证指数")                    # ① 取数（缓存→自动下载+体检）
assert_no_lookahead(signals.sig_crash, df)          # 因果性门禁（新信号必过）
trades, eq = run_backtest(df, signals.sig_crash,    # ④ 引擎（T+1、成本、记账）
                          ExitSpec(take_profit=0.05, max_hold=20).to_fn(),
                          start="2018-07-01")
# 需要期末持仓状态（买入日/浮盈/是否待成交）时用 run_backtest_ex，多返回一个 tail dict
```

**离场三种给法**（细节见 quant/exits.py 文档串）：
- `ExitSpec(take_profit=0.05, stop_loss=None, max_hold=20, trail_activate=None, trail_pct=None, min_hold=0)` 参数工厂（覆盖 90% 场景；基金记得 min_hold≥5）
- 现成函数：`exit_below_ma(20)` / `exit_trailing(0.10)`
- 自定义：`def fn(position, row, hist) -> str | None`（hist 只含截至当日数据，物理防未来函数）

**校验状态**：✅ 已验证（2026-07-25，`python test_framework.py` 全绿）：
与归档 v3 引擎逐笔回归 28 组（6 信号 × 2 指数 × 4 离场）完全一致；文档 v3 数字
原样复现；6 信号全过因果门禁 + `shift(-1)` 负例被抓；无缓存自动下载/报错契约通过；
茅台 qfq / 基金净值模式（min_hold≥5）跑通；每模块 <150 行。
**注意事项**：
- 未处理涨跌停无法成交（指数/ETF 策略影响小；个股策略报告需自行注明）
- 回测区间之外的预热段必须保留在 df 里（指标要"暖机"），用 `start=` 切回测起点
- 结果样本小（信号稀疏策略 8 年仅 10-30 笔），年化差异 <2% 视为噪声

### quant/portfolio.py + quant/rebalance.py — 多标的组合引擎（plans/16 建，plans/17 定契约）

**功能**：单标的引擎（engine.py）回答"什么时候全仓进出"（择时）；本引擎回答
"钱在几只标的之间怎么分、什么时候重新分"（配置）。
**契约与单标的对齐**：单标的策略给两个布尔判断（是否买/是否卖），组合策略给
一个**决策函数**——今天每只买多少钱、卖多少钱：

```python
decide_fn(ctx) -> {标的: 带符号金额}   # 正=买入金额，负=卖出金额，None/{}=不动
```

**签名**：
```python
from quant.portfolio import run_portfolio_backtest, load_portfolio_navs
from quant.rebalance import threshold_rebalance, buy_and_hold, periodic_rebalance

navs = load_portfolio_navs({"纳指": "fund:270042", "黄金": "fund:000216"})  # 取数走 data 层
eq, weights, log = run_portfolio_backtest(
    navs,                                        # {名称: df(date索引, close列)}
    threshold_rebalance(weights=None, threshold=0.03, min_trade_value=0),
    start=None,          # None=全部成分都有数据的首日
    cost=0.001,          # 单边成本（与 engine.py 同口径）
    initial_cash=10000.0)
# eq: 每日总资产 Series（attrs["总成本"]/["建仓日"]）；weights: 每日权重表
#     （attrs 附归因原料 shares/cash/prices/pnl）；
# log: 成交日志（第一行=建仓，之后每行一次调仓：日期/成交总额/成本/各标的带符号金额
#      「调仓-X」/上一段各腿持有损益「贡献-X」）
```

**三个现成决策函数**（`quant/rebalance.py`，都带 `.desc/.factory/.params` 标签供报告
回显和参数扫描）：`threshold_rebalance(阈值触发)` / `buy_and_hold(对照组)` /
`periodic_rebalance(freq="Y"/"Q"/"M")`。自定义只需写一个 `decide(ctx)` 函数，
ctx 提供 `date/prices/hist/shares/cash/values/total/weights/invested` 和
`orders_for_weights(目标权重)`（把"我想要的权重"翻译成"该买卖多少钱"）。

**纪律（策略无权改，写死在引擎里）**：T 日决策 → **T+1 成交**；先卖后买；
双边扣费；买不超现金、卖不超持仓（自动截断，不许透支/裸卖空）；
ffill 只用过去数据对齐日期；起点早于最晚上市成分时明确报错。

**文件分工**（每模块 <150 行的硬约束下拆开的，契约没变）：
`portfolio.py` 事件循环 / `portfolio_data.py` 取数+日期对齐+`PortfolioContext` 快照
（`from quant.portfolio import load_portfolio_navs, align_prices` 仍可用，已转出）/
`rebalance.py` 决策函数工厂 / `report_portfolio.py` 报告总装 +
`report_portfolio_parts.py` 报告零件（绩效行/成交明细/权重漂移/阈值敏感性）。
**校验状态**：✅ 2026-07-28 `python test_portfolio.py` 10 项全过（账目守恒/权重回目标/
T+1 成交/成本生效/起点校验/权重校验/不透支不卖空/ctx 看不到未来/注册表可跑/分腿归因守恒）。
**注意事项**：`log` 第一行是**建仓**不是调仓（统计再平衡次数要 `len(log)-1`）；
各标的金额**带符号**（正买负卖），"成交总额"是双边合计（|买|+|卖|）不是净划转额。

### attribution — 组合收益归因（钱是哪条腿赚的）（plans/23）

**功能**：把组合的总盈亏拆到每条腿头上——**金额法**，
`某腿当日损益 = 昨日收盘份数 × (今日净值 − 昨日净值)`。
**为什么需要**：组合是动态持仓（权重漂移 + 再平衡削减），"涨得最多的"和
"赚得最多的"经常不是同一只。longterm_balance 里纳指自己涨 +653.7%，贡献只占 40.0%。

**签名**（三个返回值原样喂进去即可，原料由引擎附带；计算在 `quant/attribution.py`，
打印在 `quant/report_attribution.py`，画图在 `quant/plot_attribution.py`）：
```python
from quant.attribution import daily_contrib, cum_contrib, summary_table, attribute_by_periods
from quant.report_attribution import print_contrib, print_attribution
from quant.plot_attribution import panel_cum_contrib

contrib = daily_contrib(eq, weights, log)      # 日度损益矩阵（各腿 + "成本"列）
cum     = cum_contrib(contrib)                 # 累计贡献（画图用，含"合计"对账线）
tbl, _  = summary_table(eq, weights, log, initial)   # 全区间总账（报告/图共用）
seg     = attribute_by_periods(contrib, eq, bounds)  # 按区间汇总（bounds=切点日期列表）
print_contrib(name, eq, weights, log, initial)               # 报告默认那块总账
print_attribution(name, eq, weights, log, initial, by="Y")   # by="rebalance" 按调仓段
panel_cum_contrib(ax, eq, weights, log)        # 把累计贡献画到任意坐标轴上
```

**已接进标准流程**（不用手动调）：组合报告默认打印总账（`print_contrib`）、
成交明细每行带"段内盈亏"、组合图第三联画累计贡献曲线、比选模式打印各配方贡献结构。
手动只在看**分段明细**时用：`python analysis/analyze_portfolio_attribution.py 配方名 rebalance`。

**校验状态**：✅ 逐日断言 `Σ各腿损益 − 成本 = 总资产变化`，且引擎记的 pnl 与
"份数×净值差"反推互相印证；`test_portfolio.py` ⑩ 项覆盖（含"日志分段贡献可拼接"
"建仓行贡献必须为 0"）。
**注意事项**：贡献是**算术金额**——元可以相加等于总盈亏，**百分比不能相加**等于总收益率
（分母不同），要百分比就除以本金；现金/空仓期贡献恒为 0（那是机会成本的样子，不是缺数据）；
成本单列不摊到成分头上（摊法有主观性）。

### strategy_as_portfolio — 择时策略 → 组合契约适配器（plans/20）

**功能**：把 `quant/strategies/` 里任意**单标的择时策略**（输出 True/False）包成
**组合决策函数**（输出金额），从而能和资产配置组合在 run.py 比选模式下**同图公平对比**。
**为什么需要**：run.py 两种模式不能混搭；而"择时 vs 死拿/配置"这个问题必须让
**同一笔钱**从头到尾交给两种打法才算比较——空仓期的现金机会成本要被算进净值里。

**签名**：
```python
from quant.adapter import strategy_as_portfolio

decide = strategy_as_portfolio(
    strategy_name,          # 策略注册名，如 "bottom_reversal"（规则从注册表取，不复制）
    asset=None,             # 对哪只标的择时；None = 组合里唯一那只
    cooldown_days=10,       # 卖后冷却交易日，与 engine.run_backtest 默认一致
    fund_mode=True)         # 基金口径：ExitSpec 的 min_hold 自动提到 5 日（惩罚性赎回费）
```

**用法示例**（配方照 `quant/portfolios/bottom_reversal_fund.py`，之后 `run.py` 填名字即跑）：
```python
PORTFOLIO = Portfolio(
    name="bottom_reversal_fund",
    holdings={"上证指数联接A": "fund:100053"},
    decide_fn=strategy_as_portfolio("bottom_reversal", fund_mode=True),
    data_start="20110101")
# python run.py --strategy longterm_balance,bottom_reversal_fund   ← 起点自动对齐到最晚就绪日
```

**核心纪律：规则只有一份。** 适配器只做**形状翻译**（信号→满仓买入金额、离场原因→清仓），
入场/离场条件仍只写在 `quant/strategies/*.py`，改一处两边同时生效。
（反面做法是手抄一份规则进 portfolios/ → 两份实现迟早漂移，回测开始骗人。）

**校验状态**：✅ 2026-07-28（plans/20）同标的同区间双引擎对照：`engine.py`（T+1 开盘）
21 笔 / 14946 元 vs 适配器（T+1 收盘）21 笔 / 13733 元，**买入日逐一对齐**（仅首笔因预热差异）
→ 证明只换了成交模型、没改策略。`test_portfolio.py` 9 项全绿。
**注意事项**：
- 与单标的引擎三处口径差异（不是 bug）：① 成交价 T+1 收盘/净值 vs T+1 开盘；
  ② **无预热段**（`ctx.hist` 从回测起点算，开头几天指标算不出 → 信号按 False）；
  ③ 冷却期在适配器里复刻，改这个参数两边就不可比了。
- **清仓下单要写 `-held * 2`**：卖单 T+1 成交，按今日市值下单在上涨日会剩尾巴，
  离场规则次日重复触发出碎单；靠引擎"卖不超过持仓"的截断兜底才干净。
- 有 `ctx.cash > 1` 的防碎单门槛：本金极小的实验（如 1 元）会 0 笔成交。
- 只传 `close` 一列（基金净值没有 OHLC）：依赖开高低/成交量的策略会明确报错，不会给假信号。

### cross_down — 信号首日触发
**功能**：条件连续多日满足时只在**首日**发信号（防"天天触发"）。
已收编进框架：`from quant.signals import cross_down`。

```python
def cross_down(cond):
    return cond & ~cond.shift(1, fill_value=False)   # 今天满足 且 昨天不满足
```

**校验状态**：✅ 已验证（2026-07-25，v2/v3 回测全量使用；框架因果门禁通过）。
**注意事项**：`cond.shift(1, fill_value=False)` 的写法可避免 pandas 新版
`fillna` 降类型的 FutureWarning（旧写法 `cond.shift(1).fillna(False)` 会报警告）。
名字叫 cross_down 但通用：金叉首日 = `cross_down(短均线 > 长均线)`。

---

## 画图

### A股配色 K 线样式

**功能**：mplfinance 的 A 股习惯配色（红涨绿跌）+ 点划线网格，复用于所有 K 线图。

```python
import mplfinance as mpf

my_color = mpf.make_marketcolors(
    up='r', down='g', edge='i', wick='i',
    volume={'up': 'red', 'down': 'green'}, ohlc='i'
)
my_style = mpf.make_mpf_style(
    marketcolors=my_color,
    gridaxis='both', gridstyle='-.',
    rc={'font.family': 'SimHei'}   # 中文字体
)

# 用法：df 的列名必须是 Open/High/Low/Close/Volume（大小写敏感），索引是日期
mpf.plot(df, type='candle', style=my_style, volume=True,
         figsize=(12, 6), title='K线', mav=(5, 10))
```

**注意事项**：
- mplfinance 要求列名严格为 `Open, High, Low, Close, Volume`，日期设为索引
- A 股习惯红涨绿跌，与欧美软件相反，别搞混

---

### plot_experiment — 回测买卖点标注图

**功能**：一次回测 → 一张标注图 PNG：收盘曲线 + 买▲/卖▼（**红/绿=盈/亏**，A股配色；
旁注卖出原因+收益率）+ 持仓段底色同胜负 + 未成交信号灰点 + 净值 vs 买入持有副图
（虚线标最大回撤峰→谷）。run.py 每次回测自动产出，文件名固定（图片查看器里刷新即可）。

**签名**：
- `plot_experiment(target, strategy_name, start, exit_override=None, data_start="20180101", cost=0.001) -> Path`
  （run.py 单策略出图入口，与 run_experiment 同参数口径）
- `plot_compare_experiment(target, strategy_names, start, exit_override=None, ...) -> Path`
  （run.py 比选入口：文字对比表 + n 个策略价格子图 + 共享净值图 + **超额收益子图**
  （策略净值÷大盘净值−1，图例带期末超额和"跑赢时间占比"））
- `plot_trades(bt, trades, eq, tail, sig, title, out_png)`（低层：拿引擎产物直接画）

**代码**：[quant/plot.py](quant/plot.py)（125 行，单策略）+ [quant/plot_compare.py](quant/plot_compare.py)（71 行，比选）。
输出 `data/trades_{代码}_{策略}.png` / `data/compare_{代码}_{策略名单}.png`。

**校验状态**：✅ 2026-07-26 上证 bottom_reversal 全区间出图，中文/标注/边界对齐目检通过；
`python test_framework.py` 全绿（模块行数 112<150）。
2026-07-26 增比选模式（plans/11）：两策略比选图目检通过，基金 min_hold 口径三入口统一
收口到 exits.adjust_for_fund。

**注意事项**：
- matplotlib Agg 后端只存图不弹窗；中文字体 SimHei/微软雅黑双保险 + `axes.unicode_minus=False`
- 卖出标注贴边自动换对齐方向（左/右）防裁剪；文字 offset points 抬高防与▼标记重叠
- 颜色语义（2026-07-26 用户反馈后定稿）：**颜色通道给胜负（红盈绿亏），卖出原因放标注
  文字**——初版用颜色编码原因（橙止盈/蓝超期），但原因文字里本来就有，颜色给胜负更直观
- 图例固定左上空白区（`bbox_to_anchor=(0, 0.87)`），别放右上（会压住右侧贴边标注）
- "信号未成交"灰点是**展示层近似**（信号次日不在成交买入日集合里即算被挡），不是引擎记账

---

## 待补充（规划中）
| 轮子 | 说明 |
|---|---|
| ~~calc_metrics~~ | ✅ 已由 quant/metrics.py 补上（2026-07-25，plans/07）：年化/回撤/夏普/卡玛/胜率/盈亏比 |
| 基准对比画图 | 策略净值 vs 基准净值归一化对比图。目前**三处重复实现**：`quote.py:_plot_return_compare`、`analysis/analyze_dividend_financing.py:report_and_plot`、`analysis/analyze_grid_etf.py:plot` → 抽成 `quant/plot_compare_bench.py` 一个函数（已登记 plans/18） |
