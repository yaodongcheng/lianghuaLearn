# -*- coding: utf-8 -*-
"""
fetch_data.py — 历史行情获取 + 本地缓存（计划 01 交付物）

教学要点（为什么这样设计）：
1. 【多源容灾】akshare 是网页接口，单一数据源可能抽风（本项目实测：东方财富
   接口在企业网络下会被防火墙间歇性断连）。所以实现"东财优先、新浪兜底"
   的双源策略——真实量化工作中，数据源容灾和交叉验证是必修课。
2. 【本地缓存】接口慢且不稳，拉一次存 data/ 目录，之后回测直接读 CSV。
3. 【统一列名】date, open, high, low, close, volume（全项目约定，见 CLAUDE.md）。
4. 【复权约定】个股前复权 qfq，指数不复权（见 Knowledge/data_sources.md）。
   前复权以最新价为基准调整历史价格，消除分红送股造成的假缺口，
   回测才不会把"除权跳水"误判成"暴跌信号"。

注意：东财与新浪的前复权因子算法略有差异，同一只票的回测请始终用同一来源
      的缓存，不要混用（一致性比来源本身更重要）。
"""

import time
from pathlib import Path

import akshare as ak
import pandas as pd
import requests

DATA_DIR = Path(__file__).parent / "data"

# 东财接口返回中文列名 → 项目统一英文列名（新浪接口本身就是英文列名，无需映射）
COLUMN_MAP = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
}

# 各类市场的默认复权方式：个股前复权，指数/ETF 不复权
# （ETF 用新浪接口没有复权参数，只能拿到未复权价——ETF 分红少但存在，长期回测需注意）
DEFAULT_ADJUST = {"a": "qfq", "idx": "", "hk": "qfq", "etf": ""}

# 缓存新鲜度容忍天数：缓存最后日期距请求结束日不超过 7 天就直接用
# （容忍周末和小长假；A股/港股最长连续休市一般不超过 7 天）
CACHE_TOLERANCE_DAYS = 7


# ============================================================
# 数据源 1（首选）：东方财富 —— akshare 的 stock_*_hist 系列
# ============================================================
def _fetch_eastmoney(market, symbol, start, end, adjust):
    if market == "a":
        return ak.stock_zh_a_hist(symbol=symbol, period="daily",
                                  start_date=start, end_date=end, adjust=adjust, timeout=15)
    if market == "idx":
        return ak.index_zh_a_hist(symbol=symbol, period="daily",
                                  start_date=start, end_date=end)
    if market == "hk":
        return ak.stock_hk_hist(symbol=symbol, period="daily",
                                start_date=start, end_date=end, adjust=adjust)
    if market == "etf":
        return ak.fund_etf_hist_em(symbol=symbol, period="daily",
                                   start_date=start, end_date=end, adjust=adjust)
    raise ValueError(f"未知市场 {market!r}")


# ============================================================
# 数据源 2（兜底）：新浪财经 —— akshare 的 stock_*_daily 系列
# ============================================================
def _sina_symbol(market, symbol):
    """新浪的代码格式带交易所前缀：sh600519 / sz000001；港股就是 00700。
    注意：A 股指数（000300 沪深300、000001 上证、000905 中证500）在新浪统一用 sh 前缀，
    写成 sz 会返回畸形数据（本项目实测踩过的坑）。"""
    if market == "hk":
        return symbol
    if market == "idx":
        # 指数：000 开头是上证系（sh000300），399 开头是深证系（sz399006 创业板指）
        return ("sz" if symbol.startswith("399") else "sh") + symbol
    if symbol.startswith(("6", "9", "5")):
        return "sh" + symbol  # 5 开头是上海场内基金/ETF（如 510210），不是股票但要走 sh
    if symbol.startswith(("4", "8")):
        return "bj" + symbol
    return "sz" + symbol  # 0/3 开头是深市个股


def _fetch_sina(market, symbol, start, end, adjust):
    sym = _sina_symbol(market, symbol)
    if market == "idx":
        df = ak.stock_zh_index_daily(symbol=sym)  # 指数无复权概念
    elif market == "etf":
        df = ak.fund_etf_hist_sina(symbol=sym)  # ETF 专用接口（A股日线接口不认 ETF）
    elif market == "a":
        df = ak.stock_zh_a_daily(symbol=sym, adjust=adjust)
    elif market == "hk":
        df = ak.stock_hk_daily(symbol=sym, adjust=adjust)
    else:
        raise ValueError(f"未知市场 {market!r}")
    # 新浪一次返回全部历史。【不要】在这里按区间过滤：
    # 缓存文件要存完整历史，过滤是 fetch_daily 返回前才做的事
    # （否则用小区间请求会把大区间缓存覆盖掉——2026-07-24 实测踩过的坑）
    return df.rename(columns=COLUMN_MAP)


SOURCES = [("东财", _fetch_eastmoney), ("新浪", _fetch_sina)]


def _fetch_with_fallback(market, symbol, start, end, adjust, retries=2):
    """依次尝试各数据源，每个源失败可重试；全部失败才报错。"""
    errors = []
    for name, fetcher in SOURCES:
        for i in range(retries):
            try:
                df = fetcher(market, symbol, start, end, adjust)
                if df is None or len(df) == 0:
                    raise ValueError("返回数据为空")
                print(f"✓ 数据源【{name}】下载成功")
                return df
            except Exception as e:
                print(f"  数据源【{name}】第 {i + 1} 次失败：{type(e).__name__}: {str(e)[:80]}")
                errors.append(f"{name}: {e}")
                if i < retries - 1:
                    time.sleep(2)
    raise RuntimeError(f"所有数据源均失败：{errors}")


def _normalize(df):
    """统一为 6 列（date, open, high, low, close, volume），日期升序。"""
    df = df.rename(columns=COLUMN_MAP)
    keep = ["date", "open", "high", "low", "close", "volume"]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise ValueError(f"返回数据缺少列 {missing}，实际列名：{list(df.columns)}")
    df = df[keep].copy()
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def fetch_daily(market, symbol, start="20200101", end=None, force_refresh=False):
    """
    拉取日线数据（优先读本地缓存，缓存过旧才重新下载）。

    参数：
        market:        "a"=A股个股 / "idx"=A股指数 / "hk"=港股个股 / "etf"=场内ETF
        symbol:        代码，如 "600519" / "000300" / "00700" / "510210"
        start, end:    "yyyymmdd" 字符串；end 默认今天
        force_refresh: True 则无视缓存强制重新下载

    返回：DataFrame，列 = date, open, high, low, close, volume，日期升序
    """
    if end is None:
        end = pd.Timestamp.today().strftime("%Y%m%d")
    if market not in DEFAULT_ADJUST:
        raise ValueError(f"未知市场 {market!r}，可选：{list(DEFAULT_ADJUST)}")

    adjust = DEFAULT_ADJUST[market]
    cache_file = DATA_DIR / f"{market}_{symbol}_{adjust or 'raw'}.csv"

    # ---- 尝试用缓存：要求 ①覆盖请求起点 ②最后日期足够新 ----
    if cache_file.exists() and not force_refresh:
        df = pd.read_csv(cache_file, parse_dates=["date"])
        # 起点判定放宽 10 天：请求的 start 可能是节假日（如 1 月 1 日），
        # 缓存第一根 K 线是其后首个交易日，严格 <= 会误判为"不覆盖"导致每次重下
        covered = df["date"].iloc[0] <= pd.Timestamp(start) + pd.Timedelta(days=10)
        fresh = df["date"].iloc[-1] >= pd.Timestamp(end) - pd.Timedelta(days=CACHE_TOLERANCE_DAYS)
        if covered and fresh:
            print(f"✓ 使用缓存 {cache_file.name}（{df['date'].iloc[0]:%Y-%m-%d} ~ "
                  f"{df['date'].iloc[-1]:%Y-%m-%d}，共 {len(df)} 行）")
            mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
            return df[mask].reset_index(drop=True)
        print("缓存不满足要求（起点不覆盖或数据过旧），重新下载…")

    # ---- 下载并写缓存 ----
    print(f"下载 {market}:{symbol} {start}~{end}（adjust={adjust!r}）…")
    raw = _fetch_with_fallback(market, symbol, start, end, adjust)
    df = _normalize(raw)

    # 关键：缓存永远存"完整区间"。若已有旧缓存，新旧合并（同日期取新值），
    # 保证缓存只增不减——之后任何区间请求都能直接读缓存，不会被小区间请求破坏
    if cache_file.exists():
        old = pd.read_csv(cache_file, parse_dates=["date"])
        df = (pd.concat([old, df])
                .drop_duplicates(subset="date", keep="last")
                .sort_values("date").reset_index(drop=True))

    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(cache_file, index=False)
    print(f"✓ 已存缓存 {cache_file.name}（{len(df)} 行，"
          f"{df['date'].iloc[0]:%Y-%m-%d} ~ {df['date'].iloc[-1]:%Y-%m-%d}）")

    # 返回前才按请求区间过滤
    mask = (df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))
    return df[mask].reset_index(drop=True)


def fetch_fund_nav(code, force_refresh=False):
    """
    拉取场外基金历史净值（东财 F10，ak.fund_open_fund_info_em），存本地缓存。

    与股票数据的本质区别（见 Knowledge/funds.md）：
    - 基金一天只有一个价（当晚公布的净值），没有开高低收
    - 所以返回列是 date, nav(单位净值), acc_nav(累计净值), daily_ret(日增长率%)
      而不是股票的 open/high/low/close/volume
    - 当日净值晚上才公布：白天看到的"估值"是第三方按重仓股估算的，不是成交价

    参数：code 为 6 位基金代码（如 "025209" 永赢先锋半导体智选混合发起C）
    """
    cache_file = DATA_DIR / f"fund_{code}.csv"
    if cache_file.exists() and not force_refresh:
        df = pd.read_csv(cache_file, parse_dates=["date"])
        fresh = df["date"].iloc[-1] >= pd.Timestamp.today() - pd.Timedelta(days=CACHE_TOLERANCE_DAYS)
        if fresh:
            print(f"✓ 使用缓存 {cache_file.name}（{df['date'].iloc[0]:%Y-%m-%d} ~ "
                  f"{df['date'].iloc[-1]:%Y-%m-%d}，共 {len(df)} 行）")
            return df

    print(f"下载基金 {code} 净值…")
    last_err = None
    for i in range(2):  # 网页接口偶发失败，重试一次
        try:
            unit = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
            acc = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
            unit = unit.rename(columns={"净值日期": "date", "单位净值": "nav", "日增长率": "daily_ret"})
            acc = acc.rename(columns={"净值日期": "date", "累计净值": "acc_nav"})
            df = unit.merge(acc[["date", "acc_nav"]], on="date", how="left")
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
            DATA_DIR.mkdir(exist_ok=True)
            df.to_csv(cache_file, index=False)
            print(f"✓ 已存缓存 {cache_file.name}（{len(df)} 行）")
            return df
        except Exception as e:
            last_err = e
            print(f"  第 {i + 1} 次下载失败：{type(e).__name__}: {str(e)[:80]}")
            time.sleep(2)
    raise RuntimeError(f"基金 {code} 净值下载失败：{last_err}")


def fetch_spot_bar(symbol="00700"):
    """
    拉港股【当日】实时快照，组装成一根日 K（6 列格式同 fetch_daily）。

    什么时候用：日 K 线接口（ak.stock_hk_daily）是批量更新，港股收盘后要等数小时
    甚至次日才能刷出当天数据；收盘后想立刻看当日行情，就用这个实时快照补一根。

    注意（重要）：
    - 结果【只在内存里用，不写缓存】——盘中它是未完成的半成品，等官方日线更新后
      以日线为准（用 force_refresh 刷新缓存即可）
    - 数据源：新浪 hq.sinajs.cn 实时行情（必须带 Referer 头，否则 403）
    - 返回 1 行 DataFrame：date, open, high, low, close, volume
    """
    url = f"https://hq.sinajs.cn/list=hk{symbol}"
    headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"  # 新浪返回 GBK 编码，不转中文名会变乱码
    # 返回形如：var hq_str_hk00700="TENCENT,腾讯控股,今开,昨收,最高,最低,现价,...";
    payload = r.text.split('="', 1)[1].rstrip('";\n')
    f = payload.split(",")
    bar = {
        "date": pd.Timestamp(f[17]),       # 日期，如 2026/07/24
        "open": float(f[2]),               # 今开
        "high": float(f[4]),               # 最高
        "low": float(f[5]),                # 最低
        "close": float(f[6]),              # 现价（收盘后=收盘价）
        "volume": float(f[12]),            # 成交量（股）
    }
    return pd.DataFrame([bar])


def check_daily(df, name=""):
    """
    数据质量快速体检。下载后务必看一眼，烂数据比没数据更危险。

    检查项：行数 / 时间范围 / 缺失值 / 重复日期 / 非正价格 / 单日极端涨跌
    （单日极端涨跌用来发现复权缺口：除权造成的假暴跌会在这里露馅）
    """
    print(f"\n===== 数据体检：{name} =====")
    print(f"行数：{len(df)}    区间：{df['date'].iloc[0]:%Y-%m-%d} ~ {df['date'].iloc[-1]:%Y-%m-%d}")
    print(f"缺失值：{int(df.isna().sum().sum())} 个    重复日期：{int(df['date'].duplicated().sum())} 个")

    bad_price = df[(df[["open", "high", "low", "close"]] <= 0).any(axis=1)]
    print(f"非正价格行数：{len(bad_price)}")

    # 单日涨跌幅 Top5（按绝对值）。前复权数据若还有"无理由的 -30%"，大概率是复权缺口
    ret = df["close"].pct_change()
    top = ret.abs().nlargest(5)
    print("单日波动 Top5（核对是否为真实事件，而非数据错误）：")
    for idx in top.index:
        print(f"  {df['date'][idx]:%Y-%m-%d}  {ret[idx]:+.1%}    "
              f"收 {df['close'][idx - 1]:.2f} → {df['close'][idx]:.2f}")


if __name__ == "__main__":
    # ===== 验证测试：腾讯控股 00700.HK，2020-01-01 至今，前复权 =====
    # 港股一年约 246~250 个交易日，2020 至今约 6.5 年 → 预期 1600 行上下
    df = fetch_daily("hk", "00700", start="20200101")
    check_daily(df, "腾讯控股 00700.HK（前复权）")
    print("\n前 3 行：")
    print(df.head(3).to_string(index=False))
    print("\n后 3 行：")
    print(df.tail(3).to_string(index=False))

    # ===== 前复权自洽性检查（不依赖外部数据）=====
    # 前复权的定义是"以最新价为基准调整历史" → qfq 的最新收盘价必须等于真实市价，
    # 历史价格则因分红调整而略低于不复权价。用这个性质验证复权是否真的生效。
    print("\n===== 前复权自洽性检查 =====")
    raw = _normalize(_fetch_sina("hk", "00700", "20200101",
                                 pd.Timestamp.today().strftime("%Y%m%d"), ""))
    same_latest = abs(raw["close"].iloc[-1] - df["close"].iloc[-1]) < 0.01
    hist_lower = df["close"].iloc[0] <= raw["close"].iloc[0] + 0.01
    print(f"qfq 最新收盘 {df['close'].iloc[-1]:.2f} vs 不复权最新收盘 {raw['close'].iloc[-1]:.2f}"
          f" → {'相等 ✓（符合前复权定义）' if same_latest else '不相等 ✗，复权可能没生效！'}")
    print(f"qfq 首日收盘 {df['close'].iloc[0]:.2f} vs 不复权首日收盘 {raw['close'].iloc[0]:.2f}"
          f" → {'qfq ≤ raw ✓（历史已向下调整）' if hist_lower else '异常 ✗'}")
