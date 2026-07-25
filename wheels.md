# 轮子库（可复用代码）

> 收录标准：在 2 个及以上场景用到、且经过正确性校验的代码。
> 每个轮子包含：**功能 / 函数签名 / 代码 / 用法示例 / 校验状态与注意事项**。
> 目前阶段用文档记录；某个板块代码量变大后，再考虑抽成 `.py` 模块。

## 目录
- [数据获取](#数据获取)
  - [fetch_daily — 日线行情获取（双源容灾 + 本地缓存）](#fetch_daily--日线行情获取双源容灾--本地缓存)
  - [quote.py — 自助行情查询 CLI](#quotepy--自助行情查询-cli)
- [技术指标](#技术指标)
  - [cal_macd — MACD 指标](#cal_macd--macd-指标)
  - [cal_kdj — KDJ 指标](#cal_kdj--kdj-指标)
- [画图](#画图)
  - [A股配色 K 线样式](#a股配色-k-线样式)
- 待补充：回测引擎、绩效指标

---

## 数据获取

### fetch_daily — 日线行情获取（双源容灾 + 本地缓存）

**功能**：拉取 A股个股 / A股指数 / 港股个股的日线行情，统一列名后存 `data/` 缓存。
东财接口优先、新浪接口兜底（实测东财在部分企业网络被防火墙拦截，见注意事项）。

**签名**：`fetch_daily(market, symbol, start="20200101", end=None, force_refresh=False) -> DataFrame`

- `market`：`"a"`=A股个股 / `"idx"`=A股指数 / `"hk"`=港股个股 / `"etf"`=场内ETF
- `symbol`：`"600519"` / `"000300"` / `"00700"` / `"510210"`
- 返回列：`date, open, high, low, close, volume`，日期升序
- 复权自动约定：个股 `qfq`，指数不复权；缓存文件名如 `hk_00700_qfq.csv`
- 缓存最后日期距今 ≤7 天直接读缓存；`force_refresh=True` 强制重下

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

## 待补充（规划中）
| 轮子 | 说明 |
|---|---|
| run_backtest | 简单事件循环回测：信号→次日成交→记现金/持仓→净值曲线 |
| calc_metrics | 年化收益、最大回撤、夏普、卡玛、胜率，对标基准 |
