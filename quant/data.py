# -*- coding: utf-8 -*-
"""
quant/data.py — ① 数据层：实验脚本永远不需要关心数据从哪来

load_data(query) 的明确契约：
1. 缓存新鲜 → 直接读缓存（fetch_data.py 轮子自己打印缓存信息）
2. 缓存缺失或过期 → 自动走 fetch_daily 双源下载（东财优先、新浪兜底），
   下载后自动 check_daily 体检（烂数据比没数据更危险）
3. 解析不了 / 下载失败 → 明确报错（不静默返回空表）
4. prepare([标的...])：实验前批量预下载，避免跑到一半断网

TARGET 合法写法：指数名"上证指数" / 股票名"贵州茅台" / 基金名"永赢半导体C" /
代码"000300" / "600519" / "00700" / "025209"。名称解析复用 quote.py 的 resolve 轮子。

基金自动切净值模式：一天只有一个价（当晚公布的净值），open=high=low=close=累计净值，
引擎的"T+1 开盘成交"在此等价于"次日净值成交"（见 Knowledge/funds.md 第三节）。
"""

import pandas as pd

from fetch_data import (CACHE_TOLERANCE_DAYS, DATA_DIR, DEFAULT_ADJUST,
                        check_daily, fetch_daily, fetch_fund_nav)
from quote import INDEX_ALIAS, resolve

# 指数代码 → 名称（quote.resolve 只按【名字】认指数，数字代码在这里补充）
# 故意不收 000001：股票（平安银行）/基金（华夏成长）/指数（上证）三方撞码，指数请写"上证指数"
INDEX_CODES = {"000300": "沪深300", "000905": "中证500", "000016": "上证50",
               "000688": "科创50", "399006": "创业板指", "000922": "中证红利"}


def _resolve_target(query):
    """标的名称/代码 → (kind, code, 名称)。解析不了就明确报错。
    撞码代码（如 007301：既是深市股票代码段又是基金代码）用前缀消歧：
    "fund:007301" 强制按基金、"stock:007301" 强制按股票。"""
    q = str(query).strip()
    for prefix, fk in (("fund:", "fund"), ("stock:", "stock")):
        if q.lower().startswith(prefix):
            code = q[len(prefix):]
            result = resolve(code, force_kind=fk)
            if result is None:
                raise ValueError(f"无法解析标的 {query!r}")
            return result
    if q in INDEX_ALIAS:
        kind, code = INDEX_ALIAS[q]
        return kind, code, q
    if q.isdigit() and q in INDEX_CODES:
        return "idx", q, INDEX_CODES[q]
    result = resolve(q)
    if result is None:
        raise ValueError(f"无法解析标的 {query!r}：换个更准确的名称或代码")
    return result


def _cache_fresh(kind, code, adjust=None):
    """缓存最后日期距今 ≤7 天算新鲜（与 fetch_data.py 的容忍度同口径）。"""
    if kind == "fund":
        f = DATA_DIR / f"fund_{code}.csv"
    else:
        adj = DEFAULT_ADJUST.get(kind, "") if adjust is None else adjust
        f = DATA_DIR / f"{kind}_{code}_{adj or 'raw'}.csv"
    if not f.exists():
        return False
    last = pd.read_csv(f, parse_dates=["date"])["date"].iloc[-1]
    return last >= pd.Timestamp.today() - pd.Timedelta(days=CACHE_TOLERANCE_DAYS)


def load_data(query, start="20180101", force_refresh=False, adjust=None):
    """取数唯一入口。返回 (df, info)：
    df   = date 索引 + open/high/low/close/volume（从 start 起，含预热段）
    info = {"kind": "a"/"idx"/"hk"/"etf"/"fund", "code": ..., "name": ...}
    adjust = 复权方式覆盖（None=默认）。ETF 回测建议 "qfq"：raw 价遇份额拆分
             会出现假暴跌（512480 两次 1拆2，详见 Knowledge/data_sources.md）。
    """
    kind, code, name = _resolve_target(query)
    fresh = _cache_fresh(kind, code, adjust) and not force_refresh

    if kind == "fund":
        raw = fetch_fund_nav(code, force_refresh=force_refresh)
        # 累计净值含历史分红，比单位净值更接近真实回报（funds.md 第四节）
        nav = raw["acc_nav"].fillna(raw["nav"]) if "acc_nav" in raw.columns else raw["nav"]
        df = pd.DataFrame({"date": raw["date"], "open": nav, "high": nav,
                           "low": nav, "close": nav, "volume": 0})
        if not fresh:
            check_daily(df, f"{name}（净值模式：开=高=低=收=累计净值）")
        print("※ 基金净值模式：一天一个价，T 日信号 → T+1 净值成交；"
              "记得 ExitSpec(min_hold≥5) 防 7 天惩罚性赎回费")
    else:
        df = fetch_daily(kind, code, start=start, force_refresh=force_refresh, adjust=adjust)
        if not fresh:
            check_daily(df, f"{name} {code}")

    df = df.set_index(pd.to_datetime(df["date"])).sort_index()
    df = df.loc[pd.Timestamp(start):]
    if len(df) == 0:
        raise ValueError(f"{name}（{code}）在 {start} 之后没有数据")
    print(f"✓ 数据就绪：{name}（{kind}:{code}）{len(df)} 行，"
          f"{df.index[0]:%Y-%m-%d} ~ {df.index[-1]:%Y-%m-%d}")
    return df, {"kind": kind, "code": code, "name": name}


def prepare(queries, start="20180101"):
    """实验前批量预下载。任何一个失败都明确报错（不静默跳过）。"""
    failed = []
    for q in queries:
        try:
            load_data(q, start=start)
        except Exception as e:
            failed.append(q)
            print(f"✗ {q} 准备失败：{type(e).__name__}: {e}")
    if failed:
        raise RuntimeError(f"prepare 失败 {len(failed)}/{len(queries)}：{failed}")
    print(f"✓ prepare 完成：{len(queries)} 个标的全部就绪")
