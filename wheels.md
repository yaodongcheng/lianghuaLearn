# 轮子库（可复用代码）

> 收录标准：在 2 个及以上场景用到、且经过正确性校验的代码。
> 每个轮子包含：**功能 / 函数签名 / 代码 / 用法示例 / 校验状态与注意事项**。
> 目前阶段用文档记录；某个板块代码量变大后，再考虑抽成 `.py` 模块。

## 目录
- [技术指标](#技术指标)
  - [cal_macd — MACD 指标](#cal_macd--macd-指标)
  - [cal_kdj — KDJ 指标](#cal_kdj--kdj-指标)
- [画图](#画图)
  - [A股配色 K 线样式](#a股配色-k-线样式)
- 待补充：数据获取（akshare 封装）、回测引擎、绩效指标

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
| fetch_data | akshare 拉取 A股/港股/指数/基金净值，统一列名，存 data/ 缓存 |
| run_backtest | 简单事件循环回测：信号→次日成交→记现金/持仓→净值曲线 |
| calc_metrics | 年化收益、最大回撤、夏普、卡玛、胜率，对标基准 |
