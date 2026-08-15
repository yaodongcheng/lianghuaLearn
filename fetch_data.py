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


def _fetch_with_fallback(market, symbol, start, end, adjust, retries=2, sources=None):
    """依次尝试各数据源，每个源失败可重试；全部失败才报错。
    sources 默认 SOURCES（东财优先、新浪兜底）；调用方可缩小范围（见 fetch_daily
    的 ETF 复权说明：新浪 ETF 接口没有复权参数，会静默返回 raw 冒充 qfq，必须排除）。"""
    errors = []
    for name, fetcher in (sources or SOURCES):
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


def fetch_daily(market, symbol, start="20200101", end=None, force_refresh=False, adjust=None):
    """
    拉取日线数据（优先读本地缓存，缓存过旧才重新下载）。

    参数：
        market:        "a"=A股个股 / "idx"=A股指数 / "hk"=港股个股 / "etf"=场内ETF
        symbol:        代码，如 "600519" / "000300" / "00700" / "510210"
        start, end:    "yyyymmdd" 字符串；end 默认今天
        force_refresh: True 则无视缓存强制重新下载
        adjust:        复权方式覆盖（None=用 DEFAULT_ADJUST 默认）。ETF 务必注意：
                       raw 价遇【份额拆分】会出现假暴跌（2026-07-27 实测 512480 两次
                       1拆2，单日假跌 -48.9%/-50.7%），回测会被污染。adjust="qfq"
                       可修复，但显式复权请求只走东财（新浪 ETF 接口无复权参数，
                       会静默返回 raw 冒充 qfq）——宁可报错，不要烂数据。

    返回：DataFrame，列 = date, open, high, low, close, volume，日期升序
    """
    if end is None:
        end = pd.Timestamp.today().strftime("%Y%m%d")
    if market not in DEFAULT_ADJUST:
        raise ValueError(f"未知市场 {market!r}，可选：{list(DEFAULT_ADJUST)}")

    if adjust is None:
        adjust = DEFAULT_ADJUST[market]
    # 显式请求复权价时排除无法兑现的源（见 docstring 的 ETF 说明）
    sources = SOURCES
    if adjust and market == "etf":
        sources = [("东财", _fetch_eastmoney)]
    cache_file = DATA_DIR / f"{market}_{symbol}_{adjust or 'raw'}.csv"

    # ---- 尝试用缓存：要求 ①覆盖请求起点 ②最后日期足够新 ----
    rescue = None   # 尾部新鲜但起点不覆盖的缓存：上市日晚于请求起点时，重新下载也
                    # 拿不到更早的数据，它只是"看起来不合格"——下载失败时它是救命稻草
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
        print("缓存不满足要求（起点不覆盖【可能是上市日晚于请求起点】或数据过旧），重新下载…")
        if fresh:
            rescue = df

    # ---- 下载并写缓存 ----
    print(f"下载 {market}:{symbol} {start}~{end}（adjust={adjust!r}）…")
    try:
        raw = _fetch_with_fallback(market, symbol, start, end, adjust, sources=sources)
    except RuntimeError:
        if rescue is not None:
            print(f"⚠ 下载失败，退回使用缓存 {cache_file.name}（起点 "
                  f"{rescue['date'].iloc[0]:%Y-%m-%d} 即为该标的全部可得历史，尾部新鲜）")
            mask = ((rescue["date"] >= pd.Timestamp(start))
                    & (rescue["date"] <= pd.Timestamp(end)))
            return rescue[mask].reset_index(drop=True)
        raise
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


def fetch_fund_rank(code):
    """
    基金同类排名快照（东财 F10，近三月口径）：返回 (同类排名, 全市场排名)，失败返回 None。

    为什么只有排名没有"同类平均涨幅"：支付宝/天天基金展示的"同类平均"曲线是平台
    按基金分类算的均值序列，免费接口拿不到稳定的逐日数据（2026-07-25 实测：
    fund_open_fund_info_em 的"同类排名走势"只返回排名，不含平均涨幅）。
    所以用排名作为"同类定位"的替代参考：同类排名靠前 ≈ 跑赢同类平均。
    不做缓存：单次调用数据量小，且排名每天变。
    """
    try:
        df = ak.fund_open_fund_info_em(symbol=code, indicator="同类排名走势")
        last = df.iloc[-1]
        return (int(last["同类型排名-每日近三月排名"]), int(last["总排名-每日近三月排名"]))
    except Exception:
        return None


def fetch_fund_purchase(keyword=None, force_refresh=False):
    """全市场场外基金的【申购状态 + 日累计限额】快照（东财 fund_purchase_em）。

    为什么需要这个轮子：QDII 基金常年受外汇额度限制，"回测跑得好"和"买得进去"是
    两件事（见 Knowledge/funds.md 四节）。限额天天变，任何写死的数字都会过期，
    所以每次要落地一只基金前先查一遍。

    参数：keyword 基金简称关键词（如 "纳斯达克"），None = 返回全市场
    返回列：code, name, status(申购状态), min_buy(购买起点元), day_limit(日累计限额元), fee
        ⚠ day_limit=0 通常表示"接口没给限额"（多为机构/特定份额），不等于不限购；
        真正能不能买以 status 为准（开放申购 / 限大额 = 能买，暂停申购 = 买不了）。
    缓存：当天一份（data/fund_purchase.csv），跨天自动重取。
    """
    cache = DATA_DIR / "fund_purchase.csv"
    fresh = cache.exists() and time.strftime("%Y-%m-%d") == time.strftime(
        "%Y-%m-%d", time.localtime(cache.stat().st_mtime))
    if fresh and not force_refresh:
        out = pd.read_csv(cache, dtype={"code": str})
    else:
        df = ak.fund_purchase_em()
        out = pd.DataFrame({
            "code": df["基金代码"].astype(str).str.zfill(6),
            "name": df["基金简称"],
            "status": df["申购状态"],
            "min_buy": pd.to_numeric(df["购买起点"], errors="coerce"),
            "day_limit": pd.to_numeric(df["日累计限定金额"], errors="coerce"),
            "fee": pd.to_numeric(df["手续费"], errors="coerce"),
        })
        out.to_csv(cache, index=False)
        print(f"✓ 申购状态表已更新：{len(out)} 只（存 {cache.name}）")
    if keyword:
        out = out[out["name"].str.contains(keyword, na=False)]
    return out.reset_index(drop=True)


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


# ============================================================
# 分红 / 融资全市场数据（计划 16，策略"分红融资比"的数据底座）
# ============================================================
# 口径教学：
# - 分红表（stock_fhps_em，按报告期查）：现金分红比例 = 每 10 股派 X 元（税前），
#   分红总额 = X/10 × 当期总股本。可查 2000 年以来的年报(1231)/中报(0630)。
# - 融资三表：IPO（2010 年起）+ 增发（2010 年起）+ 配股（1991 年起）。
#   注意单位不同：IPO 发行总数=万股，增发/配股=股——换算已在代码里注明。
# - 已知缺口（回测报告必须披露）：2010 年前 IPO/增发缺失 → 老股融资被低估、
#   分红融资比被高估（方向性偏差：更偏向选入老牌分红股）。
DIVFIN_DIR = DATA_DIR / "dividend_financing"


def fetch_dividend_table(period, force_refresh=False):
    """拉取全市场某报告期的分红配送表（东财 stock_fhps_em），缓存到 CSV。

    参数：period 报告期 "yyyymmdd"——年报 "20201231"，中报 "20200630"。
    返回列：code, name, div_per_10(每10股派息元), total_shares(总股本), ex_date(除权除息日)
    ——每笔分红的"金额与日期"都在这里，point-in-time 选股按 ex_date 过滤即可。
    """
    DIVFIN_DIR.mkdir(exist_ok=True)
    cache = DIVFIN_DIR / f"fhps_{period}.csv"
    if cache.exists() and not force_refresh:
        return pd.read_csv(cache, parse_dates=["ex_date"], dtype={"code": str})
    df = ak.stock_fhps_em(date=period)
    out = pd.DataFrame({
        "code": df["代码"].astype(str).str.zfill(6),
        "name": df["名称"],
        "div_per_10": pd.to_numeric(df["现金分红-现金分红比例"], errors="coerce"),
        "total_shares": pd.to_numeric(df["总股本"], errors="coerce"),
        "ex_date": pd.to_datetime(df["除权除息日"], errors="coerce"),
    })
    out = out.dropna(subset=["div_per_10", "total_shares"])
    out = out[out["div_per_10"] > 0]  # 只留真金白银的现金分红（送转股不算回馈现金）
    out.to_csv(cache, index=False)
    print(f"✓ 分红表 {period}：{len(out)} 只有现金分红（存 {cache.name}）")
    return out


def fetch_financing_tables(force_refresh=False):
    """拉取全市场融资三表（IPO/增发/配股），统一成 (code, date, amount) 长表。

    amount = 该次从股民手中募走的钱（元）。三表合并返回一个 DataFrame，
    多一列 kind 区分来源（ipo/secondary/rights），便于审计。
    """
    DIVFIN_DIR.mkdir(exist_ok=True)
    cache = DIVFIN_DIR / "financing_all.csv"
    if cache.exists() and not force_refresh:
        return pd.read_csv(cache, parse_dates=["date", "list_date"],
                           dtype={"code": str})

    parts = []
    # —— IPO：发行总数(万股) × 发行价(元) ——
    ipo = ak.stock_xgsglb_em(symbol="全部股票")
    ipo_amt = (pd.to_numeric(ipo["发行总数"], errors="coerce") * 1e4
               * pd.to_numeric(ipo["发行价格"], errors="coerce"))
    parts.append(pd.DataFrame({
        "code": ipo["股票代码"].astype(str).str.zfill(6),
        "date": pd.to_datetime(ipo["上市日期"], errors="coerce"),
        "amount": ipo_amt, "kind": "ipo",
        "list_date": pd.to_datetime(ipo["上市日期"], errors="coerce"),
    }))
    # —— 增发：发行总数(股) × 发行价 ——
    zf = ak.stock_qbzf_em()
    zf_amt = (pd.to_numeric(zf["发行总数"], errors="coerce")
              * pd.to_numeric(zf["发行价格"], errors="coerce"))
    parts.append(pd.DataFrame({
        "code": zf["股票代码"].astype(str).str.zfill(6),
        "date": pd.to_datetime(zf["发行日期"], errors="coerce"),
        "amount": zf_amt, "kind": "secondary", "list_date": pd.NaT,
    }))
    # —— 配股：配股数量(股) × 配股价 ——
    pg = ak.stock_pg_em()
    pg_amt = (pd.to_numeric(pg["配股数量"], errors="coerce")
              * pd.to_numeric(pg["配股价"], errors="coerce"))
    parts.append(pd.DataFrame({
        "code": pg["股票代码"].astype(str).str.zfill(6),
        "date": pd.to_datetime(pg["股权登记日"], errors="coerce"),
        "amount": pg_amt, "kind": "rights", "list_date": pd.NaT,
    }))

    out = (pd.concat(parts, ignore_index=True)
             .dropna(subset=["amount", "date"]))
    out = out[out["amount"] > 0]
    # 合理性体检：单笔募资应在千万~几千亿之间，超出说明单位搞错了
    lo, hi = out["amount"].min(), out["amount"].max()
    assert lo > 1e6 and hi < 1e12, f"募资额量级异常：{lo:.0f} ~ {hi:.0f}，检查单位"
    out.to_csv(cache, index=False)
    print(f"✓ 融资三表：IPO {sum(out['kind'] == 'ipo')} 笔、增发 "
          f"{sum(out['kind'] == 'secondary')} 笔、配股 {sum(out['kind'] == 'rights')} 笔"
          f"（存 {cache.name}）")
    return out


def fetch_ipo_amount(codes, as_of=None):
    """逐股补全 IPO 募资额（元），补 fetch_financing_tables 里 2010 年前的缺口。

    参数：codes 股票代码列表；as_of 只认上市日 ≤ 该日的募资（防未来函数，None=不限）。
    返回 (ok: {code: 募资额(元)}, failed: [code])——**失败的单独返回，绝不当 0**。

    为什么这个轮子必须带缓存 + 重试 + 显式失败（2026-07-27 实测踩坑）：
    这是网页逐股接口（stock_ipo_summary_cninfo），偶发失败。初版把失败静默当 0，
    该股融资就只剩配股零头，分红融资比虚高几十倍（建设银行：真 IPO 571 亿，
    失败时只剩 2010 年配股 22 亿，比率从 ~14 虚高到 ~359，排名从进不了榜跳到第 1）
    ——**静默的数据失败不是缺失，是篡改**。所以：
    ① 成功结果缓存 audit_ipo.csv（跨次重跑结果一致=可复现）；
    ② 失败重试 3 次；③ 仍失败的进 failed，调用方自行剔除（宁缺毋假）。
    注意 amt=0（查到了但金额为 0/上市日晚于 as_of）也会入缓存——那是确定结论，别重查。
    """
    DIVFIN_DIR.mkdir(exist_ok=True)
    cache = DIVFIN_DIR / "audit_ipo.csv"
    as_of = pd.Timestamp(as_of) if as_of is not None else None
    hit = {}
    if cache.exists():
        kdf = pd.read_csv(cache, dtype={"code": str})
        known = dict(zip(kdf["code"], kdf["ipo_amount"]))
        hit = {c: known[c] for c in codes if c in known}
    todo = [c for c in codes if c not in hit]
    result, failed = dict(hit), []
    for i, code in enumerate(todo):
        amt = None
        for _attempt in range(3):                    # 网页接口偶发失败，重试 3 次
            try:
                df = ak.stock_ipo_summary_cninfo(symbol=code)
                a = pd.to_numeric(df["募集资金净额"], errors="coerce").iloc[0]
                d = pd.to_datetime(df["上市日期"], errors="coerce").iloc[0]
                # 逐股接口单位是【万元】；上市日晚于选股日的募资不算（防未来函数）
                ok_date = as_of is None or (pd.notna(d) and d <= as_of)
                amt = a * 1e4 if pd.notna(a) and ok_date else 0.0
                break
            except Exception:
                time.sleep(1)
        if amt is None:
            failed.append(code)
        else:
            result[code] = amt
        if (i + 1) % 50 == 0:
            print(f"  IPO 补全进度 {i + 1}/{len(todo)}（缓存命中 {len(hit)} 只）")
    if todo:                                          # 增量写缓存
        new = pd.DataFrame({"code": list(result.keys()),
                            "ipo_amount": list(result.values())})
        old = (pd.read_csv(cache, dtype={"code": str}) if cache.exists()
               else pd.DataFrame({"code": [], "ipo_amount": []}))
        (pd.concat([old, new]).drop_duplicates("code", keep="last")
           .to_csv(cache, index=False))
    return result, failed


def fetch_index_daily_tx(code):
    """指数日线全历史（腾讯源），返回统一列名 date/open/high/low/close/volume。

    为什么需要第三个源（2026-08-06 实测踩坑）：fetch_daily 的双源里，东财在企业
    网络下被防火墙间歇断连（当天 2 连败），新浪对部分中证指数只回传多年前的旧数据
    ——旧缓存还在、看着"下载成功"，数据其实是脏的。腾讯源能取到 2005 年至今全量。
    用量小不落缓存，每次现拉；个股日线仍优先 fetch_daily（要复权和缓存）。
    """
    df = ak.stock_zh_index_daily_tx(symbol=f"sh{code}")
    df["volume"] = df["amount"]          # 腾讯列名是 amount，补成项目统一列名
    return df[["date", "open", "high", "low", "close", "volume"]]


def fetch_index_value_csindex(code):
    """指数估值（中证指数公司官网）：市盈率1/2、股息率1/2。

    注意：官网这份 Excel **只含近 20 个交易日**，没有长历史分位可算——用前
    先看行数，别拿它算"历史分位"（2026-08-06 实测踩坑，20 天窗口的分位是
    假指标）。对红利指数，"贵不贵"看股息率不点位（买红利=买分红）：估值判断
    用经验阈值（股息率 ≥4.5% 正常偏高 / <3.5% 偏贵），见
    analysis/analyze_hongli_valuation.py 头注释。
    官网页脚说明：市盈率1/股息率1 按最近年报口径（静态），2 号按近 12 个月
    滚动（动态、更贴当前）。列名为中文（日期/市盈率1/市盈率2/股息率1/股息率2）。
    """
    df = ak.stock_zh_index_value_csindex(symbol=code)
    df["日期"] = pd.to_datetime(df["日期"])
    return df


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
