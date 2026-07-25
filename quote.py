# -*- coding: utf-8 -*-
"""
quote.py — 自助行情查询工具（股票/港股/指数/基金，名称或代码均可）

用法（在终端运行，支持中文名）：
    python quote.py 腾讯            # 港股，按名称
    python quote.py 00700           # 港股，按代码（5 位）
    python quote.py 贵州茅台        # A股，按名称
    python quote.py 600519          # A股，按代码（6 位）
    python quote.py 沪深300         # 指数，按别名
    python quote.py 025209          # 基金，按代码（6 位）
    python quote.py 永赢先锋半导体  # 基金，按名称（会列出 A/C 让你选）
    python quote.py                 # 不带参数 → 交互式输入
    python quote.py 000001          # 代码撞车时（股票和基金都有 000001）会提示你加：
    python quote.py 000001 --stock  /  python quote.py 000001 --fund
    追加 --refresh 可强制重新下载（默认读本地缓存，秒回）

    区间与对比：
    python quote.py 腾讯 --days 365              # 近一年 K 线
    python quote.py 025209 --days 365 --bench    # 近一年收益率 vs 沪深300（一张图）
    python quote.py 013286 --bench 上证指数      # 全区间收益率 vs 指定基准

输出：最近 10 行数据 + 关键数字 + 一张图（存 data/quote_*.png，会打印路径）。
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import requests

from fetch_data import DATA_DIR, fetch_daily, fetch_fund_nav, fetch_spot_bar
from plot_kline import my_style  # 复用 K 线样式轮子

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# 指数别名 → (market, code)。只按【名字】收录：000001 这种数字代码谁输谁就是想买股票
INDEX_ALIAS = {
    "沪深300": ("idx", "000300"), "上证指数": ("idx", "000001"),
    "中证500": ("idx", "000905"), "创业板指": ("idx", "399006"),
    "上证50": ("idx", "000016"), "科创50": ("idx", "000688"),
}


# ============================================================
# 名称 → 代码 解析
# ============================================================
def _sina_suggest(keyword, type_code):
    """新浪联想接口：按名称或代码搜。type: 111=A股, 31=港股, 21=基金
    返回 [(中文名, 代码)]——按代码搜时首个字段可能是 sh600519 这种，所以
    从各字段里挑第一个含中文的作为显示名"""
    r = requests.get(
        f"https://suggest3.sinajs.cn/suggest/type={type_code}&key={keyword}",
        headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"},
        timeout=10)
    r.encoding = "gbk"
    payload = r.text.split('="', 1)[1].rstrip('";\n')
    hits = []
    for item in payload.split(";"):
        f = item.split(",")
        if len(f) >= 4 and f[2]:
            cjk = next((x for x in f if any('一' <= ch <= '鿿' for ch in x)), f[0])
            hits.append((cjk, f[2]))
    return hits


def _fund_list():
    """基金全名单（东财），缓存 7 天——2 万多条，每次都拉太慢"""
    cache = DATA_DIR / "_fund_list.csv"
    if cache.exists():
        age_days = (pd.Timestamp.now() - pd.Timestamp(cache.stat().st_mtime, unit="s")).days
        if age_days < 7:
            return pd.read_csv(cache, dtype=str)
    import akshare as ak
    df = ak.fund_name_em()
    df.to_csv(cache, index=False)
    return df


def _display_name(kind, code):
    """数字代码 → 显示用名称（查不到就用代码本身，不影响功能）"""
    try:
        if kind == "fund":
            funds = _fund_list()
            hit = funds[funds["基金代码"] == code]
            if len(hit):
                return hit.iloc[0]["基金简称"]
        elif kind == "a":
            hits = _sina_suggest(code, "111")
            if hits:
                return hits[0][0]
        elif kind == "hk":
            hits = _sina_suggest(code, "31")
            if hits:
                return hits[0][0]
        elif kind == "idx":
            for alias, (_, c) in INDEX_ALIAS.items():
                if c == code:
                    return alias
    except Exception:
        pass
    return code


def resolve(query, force_kind=None):
    """
    把用户输入解析成 (kind, code, 名称)。kind ∈ {"a","idx","hk","fund"}。
    解析不了或有歧义时打印提示并返回 None。
    """
    q = query.strip()

    # ① 指数别名（按名字）
    if q in INDEX_ALIAS:
        kind, code = INDEX_ALIAS[q]
        return kind, code, q

    # ② 纯数字代码
    if q.isdigit():
        if len(q) <= 5:  # 港股代码是 5 位（0700 也能认，补零）
            return "hk", q.zfill(5), q
        # 6 位：可能是 A股/场内ETF，也可能是场外基金——撞车时让用户指明
        kinds = []
        if not force_kind:
            if q.startswith(("51", "15", "56", "58", "16")):
                kinds = ["etf"]  # 51/56/58 上海、15/16 深圳：场内基金代码段
            elif q.startswith(("60", "68", "00", "30", "43", "83", "87", "88", "92")):
                kinds.append("a")
            kinds.append("fund")
            if len(kinds) > 1:
                try:  # 查基金名单里有没有它；没有就不是歧义
                    funds = _fund_list()
                    if q not in set(funds["基金代码"]):
                        kinds = ["a"] if "a" in kinds else []
                except Exception:
                    pass
            if len(kinds) > 1 and "a" in kinds and "fund" in kinds:
                print(f"⚠ 代码 {q} 有歧义：A股和基金都可能是它。请追加 --stock 或 --fund 再试")
                return None
            if not kinds:
                print(f"⚠ 无法识别代码 {q}（既不是常见 A股前缀，基金名单里也没有）")
                return None
            kind = kinds[0]
        else:
            kind = "a" if force_kind == "stock" else "fund"
        return kind, q, q

    # ③ 名称：依次搜 A股 → 港股 → 基金，找到即止
    # （港股排在基金前：搜"腾讯"的人要的是 00700，不是名字里带"腾讯"的基金；
    #   想直接搜基金可加 --fund 跳过股票搜索）
    if force_kind != "fund":
        hits_a = _sina_suggest(q, "111")
        if hits_a:
            name, full = hits_a[0]
            code = full[-6:]
            extra = f"（另有匹配：{', '.join(n for n, _ in hits_a[1:4])}）" if len(hits_a) > 1 else ""
            print(f"按名称匹配到 A股：{name}（{code}）{extra}")
            return "a", code, name

        hits_hk = _sina_suggest(q, "31")
        if hits_hk:
            name, code = hits_hk[0]
            print(f"按名称匹配到港股：{name}（{code}）")
            return "hk", code, name

    if force_kind != "stock":
        try:
            funds = _fund_list()
            hit = funds[funds["基金简称"].str.contains(q, na=False)]
            if len(hit) == 1:
                row = hit.iloc[0]
                print(f"按名称匹配到基金：{row['基金简称']}（{row['基金代码']}）")
                return "fund", row["基金代码"], row["基金简称"]
            if len(hit) > 1:
                print(f"⚠ 匹配到 {len(hit)} 只基金，请用 6 位代码指定（前 8 个候选）：")
                for _, r in hit.head(8).iterrows():
                    print(f"    {r['基金代码']}  {r['基金简称']}（{r['基金类型']}）")
                return None
        except Exception as e:
            print(f"（基金名单不可用：{e}，跳过基金搜索）")

    print(f"⚠ 没找到「{q}」：A股/港股/基金都搜不到，试试更准确的名称或代码")
    return None


# ============================================================
# 展示：最近数据 + 关键数字 + 图
# ============================================================
def _plot_return_compare(dates, ret_a, label_a, ret_b, label_b, title, out):
    """双序列收益率对比图（都从 0% 起步）——基金/股票 vs 基准通用"""
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(dates, ret_a * 100, label=label_a, linewidth=1.5)
    ax.plot(dates, ret_b * 100, label=label_b, linewidth=1.2, alpha=0.85)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.legend()
    ax.grid(linestyle="-.", alpha=0.5)
    ax.set_title(title)
    ax.set_ylabel("区间累计收益率 (%)")
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _window(df, days):
    """截取最近 N 个自然日（days=None 则全量）"""
    if not days:
        return df
    return df[df["date"] >= df["date"].iloc[-1] - pd.Timedelta(days=days)].reset_index(drop=True)


def show_fund(code, name, days=None, bench_code=None):
    df = fetch_fund_nav(code)
    w = _window(df, days)
    print(f"\n最近 10 天净值（{name} {code}）：")
    print(w.tail(10).to_string(index=False))
    latest = w.iloc[-1]
    print(f"\n最新净值 {latest['nav']:.4f}（{latest['date']:%Y-%m-%d}，当晚才公布，白天看到的是估值）")

    out = DATA_DIR / f"quote_fund_{code}.png"
    if bench_code:
        # 叠加基准：对齐日期、双方归一化为"区间收益率"
        idx = fetch_daily("idx", bench_code, start=w["date"].iloc[0].strftime("%Y%m%d"))
        m = w[["date", "nav"]].merge(idx[["date", "close"]], on="date", how="inner")
        bench_name = _display_name("idx", bench_code)
        ret_f = m["nav"] / m["nav"].iloc[0] - 1
        ret_b = m["close"] / m["close"].iloc[0] - 1
        print(f"区间（{m['date'].iloc[0]:%Y-%m-%d} 起）：基金 {ret_f.iloc[-1]:+.1%}    "
              f"{bench_name} {ret_b.iloc[-1]:+.1%}    超额 {ret_f.iloc[-1] - ret_b.iloc[-1]:+.1%}")
        _plot_return_compare(m["date"], ret_f, f"{name}（{code}）", ret_b, bench_name,
                             f"{name} vs {bench_name}（区间收益率对比）", out)
    else:
        if len(w) > 20:
            print(f"近 20 日：{latest['nav'] / w['nav'].iloc[-21] - 1:+.1%}    "
                  f"成立以来：{latest['nav'] / df['nav'].iloc[0] - 1:+.1%}")
        fig, ax = plt.subplots(figsize=(12, 4.5))
        ax.plot(w["date"], w["nav"], linewidth=1.3)
        ax.set_title(f"{name}（{code}）单位净值")
        ax.grid(linestyle="-.", alpha=0.5)
        fig.savefig(out, dpi=120, bbox_inches="tight")
        plt.close(fig)
    print(f"图已保存：{out}")


def show_stock(kind, code, name, refresh=False, days=None, bench_code=None):
    df = fetch_daily(kind, code, force_refresh=refresh)
    note = ""
    if kind == "hk":  # 港股日K线更新慢，收盘后可用实时快照补当日
        spot = fetch_spot_bar(code)
        if spot["date"].iloc[0] > df["date"].max():
            df = pd.concat([df, spot], ignore_index=True)
            note = "（最后一根是当日实时快照，未入缓存）"

    print(f"\n最近 10 天（{name} {code}）{note}：")
    print(df.tail(10).to_string(index=False))
    c = df["close"]
    if len(df) > 21:
        print(f"\n最新收盘 {c.iloc[-1]:.2f}（{df['date'].iloc[-1]:%Y-%m-%d}）    "
              f"近 5 日：{c.iloc[-1] / c.iloc[-6] - 1:+.1%}    "
              f"近 20 日：{c.iloc[-1] / c.iloc[-21] - 1:+.1%}")

    out = DATA_DIR / f"quote_{kind}_{code}.png"
    if bench_code:
        # 叠加基准对比：改用收益率曲线（K 线和收益率不同尺度，不能混画）
        w = _window(df, days)
        idx = fetch_daily("idx", bench_code, start=w["date"].iloc[0].strftime("%Y%m%d"))
        m = w[["date", "close"]].merge(idx[["date", "close"]], on="date",
                                       how="inner", suffixes=("", "_b"))
        bench_name = _display_name("idx", bench_code)
        ret_s = m["close"] / m["close"].iloc[0] - 1
        ret_b = m["close_b"] / m["close_b"].iloc[0] - 1
        print(f"区间（{m['date'].iloc[0]:%Y-%m-%d} 起）：{name} {ret_s.iloc[-1]:+.1%}    "
              f"{bench_name} {ret_b.iloc[-1]:+.1%}    超额 {ret_s.iloc[-1] - ret_b.iloc[-1]:+.1%}")
        _plot_return_compare(m["date"], ret_s, f"{name}（{code}）", ret_b, bench_name,
                             f"{name} vs {bench_name}（区间收益率对比）", out)
    else:
        k = (_window(df, days) if days else df.tail(60)).set_index("date").rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        mpf.plot(k, type="candle", style=my_style, volume=True, figsize=(12, 6),
                 title=f"{name} {code}", mav=(5, 10, 20),
                 savefig=dict(fname=out, dpi=120, bbox_inches="tight"))
    print(f"图已保存：{out}")


def main():
    args, days, bench_code, refresh, force_kind = [], None, None, False, None
    i = 1
    while i < len(sys.argv):
        t = sys.argv[i]
        if t == "--days":                       # 近 N 个自然日
            days = int(sys.argv[i + 1]); i += 2
        elif t == "--bench":                    # 叠加基准对比，可跟指数别名（默认沪深300）
            bench_code = "000300"
            if i + 1 < len(sys.argv) and sys.argv[i + 1] in INDEX_ALIAS:
                bench_code = INDEX_ALIAS[sys.argv[i + 1]][1]; i += 1
            i += 1
        elif t == "--refresh":
            refresh = True; i += 1
        elif t == "--stock":
            force_kind = "stock"; i += 1
        elif t == "--fund":
            force_kind = "fund"; i += 1
        else:
            args.append(t); i += 1

    if args:
        query = args[0]
    else:
        print(__doc__)
        query = input("请输入股票/指数/基金的名称或代码：").strip()
        if not query:
            return

    result = resolve(query, force_kind)
    if not result:
        return
    kind, code, name = result
    if name == code:  # 数字代码输入时，反查一个好看的名称用于展示
        name = _display_name(kind, code)
    if kind == "fund":
        show_fund(code, name, days, bench_code)
    else:
        show_stock(kind, code, name, refresh, days, bench_code)


if __name__ == "__main__":
    main()
