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
    python quote.py 025209 --days 365            # 基金图表只看近一年
    python quote.py 014143 --bench 中证500       # 换对比基准（指数别名或 6 位指数代码）
    基金默认自动对比沪深300：区间收益一览（近1周/1月/3月/6月/1年/成立以来）
    + 近10日逐日涨跌幅对比 + 三面板图（净值 / 累计收益率 / 每日涨跌幅）。

    图保存到 data/quote_*.png 并自动打开（--no-open 可关闭）。
"""

import os
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import requests

from fetch_data import DATA_DIR, fetch_daily, fetch_fund_nav, fetch_fund_rank, fetch_spot_bar
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


def _open_image(path):
    """用系统默认看图软件打开图片。失败只提示一句，不影响主流程。"""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        print(f"（图片自动打开失败：{e}，请按上面的路径手动打开）")


def _pct(x):
    """收益率（小数）格式化为 +x.x%；None/NaN 显示为 —"""
    return "—" if x is None or pd.isna(x) else f"{x:+.1%}"


# 基金"区间收益一览"的固定窗口（自然日口径，和支付宝/天天基金的展示习惯一致）
FUND_PERIODS = [("近1周", 7), ("近1月", 30), ("近3月", 91),
                ("近6月", 182), ("近1年", 365), ("成立以来", None)]


def _fund_daily_ret(df):
    """基金日收益率（小数）。优先用官方"日增长率"列（含分红处理，最准，见 funds.md），
    缺失或旧缓存没有该列时用单位净值 pct_change 兜底。"""
    fallback = df["nav"].pct_change() * 100
    if "daily_ret" in df.columns:
        r = pd.to_numeric(df["daily_ret"], errors="coerce").fillna(fallback)
    else:
        r = fallback
    return (r.fillna(0) / 100).reset_index(drop=True)


def show_fund(code, name, days=None, bench_code=None, open_img=True):
    df = fetch_fund_nav(code).sort_values("date").reset_index(drop=True)
    df["r"] = _fund_daily_ret(df)

    # 基金默认对比沪深300。为什么不做"行业指数"自动对比：主动基金没有官方"所属行业
    # 指数"（持仓一季度才披露一次且会变）；实测东财同类接口只给排名、不给同类平均涨幅，
    # 所以同类定位用排名，行业对比交给 --bench 手动指定（见 Knowledge/funds.md）
    bench_is_default = bench_code is None
    if bench_code is None:
        bench_code = "000300"
    bench = None
    try:
        bench = fetch_daily("idx", bench_code, start=df["date"].iloc[0].strftime("%Y%m%d"))
    except Exception as e:
        print(f"⚠ 基准指数 {bench_code} 拉取失败（{type(e).__name__}: {str(e)[:60]}），本次只看基金自身")
    bench_name = _display_name("idx", bench_code)

    # ---- 头部信息 ----
    try:
        ftype = _fund_list().loc[lambda f: f["基金代码"] == code, "基金类型"].iloc[0]
    except Exception:
        ftype = ""
    latest = df.iloc[-1]
    bench_note = "（默认，--bench 可换）" if bench_is_default and bench is not None else ""
    print(f"\n{name}（{code}）{ftype}    对比基准：{bench_name}{bench_note}")
    print(f"最新净值 {latest['nav']:.4f}（{latest['date']:%Y-%m-%d}，当晚才公布，白天看到的是估值）")

    # ---- 区间收益一览（支付宝风格）：基金按日增长率连乘（最准），基准按收盘价 ----
    last, first = df["date"].iloc[-1], df["date"].iloc[0]
    print(f"\n区间收益一览（截至 {last:%Y-%m-%d}）：")
    for label, span in FUND_PERIODS:
        start = first if span is None else last - pd.Timedelta(days=span)
        if start < first:
            print(f"  {label}：成立不足，暂无")
            continue
        fret = (1 + df.loc[df["date"] >= start, "r"]).prod() - 1
        line = f"  {label}：基金 {_pct(fret)}"
        if bench is not None:
            bsub = bench[bench["date"] >= start]
            bret = (bsub["close"].iloc[-1] / bsub["close"].iloc[0] - 1) if len(bsub) >= 2 else None
            line += f"    {bench_name} {_pct(bret)}"
            if bret is not None:
                line += f"    超额 {_pct(fret - bret)}"
        print(line)

    # ---- 近 10 日逐日涨跌幅对比 ----
    print("\n近 10 日逐日涨跌幅：")
    tail = df.tail(10)[["date", "nav", "r"]]
    if bench is not None:
        b = bench[["date", "close"]].copy()
        b["br"] = b["close"].pct_change()
        tail = tail.merge(b[["date", "br"]], on="date", how="left")
    for _, row in tail.iterrows():
        line = f"  {row['date']:%Y-%m-%d}  净值 {row['nav']:.4f}  基金 {row['r']:+.2%}"
        if "br" in row.index:
            line += f"    {bench_name} {_pct(row['br'])}"
        print(line)

    # ---- 同类排名（"同类平均涨幅"拿不到，用排名做同类定位参考）----
    rk = fetch_fund_rank(code)
    if rk:
        print(f"\n近三月同类排名：第 {rk[0]} 名（全市场第 {rk[1]} 名，东财口径）——排名靠前 ≈ 跑赢同类")

    # ---- 图：上=单位净值，下=窗口内累计收益率对比 ----
    w = _window(df, days)
    if len(w) < 2:
        w = df
    out = DATA_DIR / f"quote_fund_{code}.png"
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    ax1.plot(w["date"], w["nav"], linewidth=1.3)
    ax1.set_title(f"{name}（{code}）单位净值")
    ax1.grid(linestyle="-.", alpha=0.5)

    m = w[["date", "r"]]
    if bench is not None:
        mb = m.merge(bench[["date", "close"]], on="date", how="inner")
        if len(mb) >= 2:  # 日期对不上（如 QDII 与 A 股假期错位）就退回只画基金
            m = mb
    cum = (1 + m["r"]).cumprod()
    ret_f = cum / cum.iloc[0] - 1
    ax2.plot(m["date"], ret_f * 100, label=name, linewidth=1.5)
    if "close" in m.columns:
        ret_b = m["close"] / m["close"].iloc[0] - 1
        ax2.plot(m["date"], ret_b * 100, label=bench_name, linewidth=1.2, alpha=0.85)
    ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax2.legend()
    span_txt = f"近 {days} 天" if days else "全部历史"
    ax2.set_title(f"区间累计收益率（{span_txt}，从 0% 起步）")
    ax2.set_ylabel("%")
    ax2.grid(linestyle="-.", alpha=0.5)

    # 每日涨跌幅：基金画柱（红涨绿跌，A 股习惯），基准画线——都是 % 单位，可以叠。
    # 这张图的看点是"波动"：柱子越高/越深说明每天上蹿下跳越厉害，
    # 两只累计收益相同的基金，波动小的那只持有体验好得多（夏普比率的直观来源）
    fr = m["r"] * 100
    ax3.bar(m["date"], fr, width=1.0,
            color=["#d62728" if x >= 0 else "#2ca02c" for x in fr], label=name)
    if "close" in m.columns:
        ax3.plot(m["date"], m["close"].pct_change() * 100,
                 linewidth=1.2, alpha=0.9, label=bench_name)
    ax3.axhline(0, color="gray", linewidth=0.8)
    ax3.legend()
    ax3.set_title("每日涨跌幅对比（看波动，不是看方向）")
    ax3.set_ylabel("%")
    ax3.grid(linestyle="-.", alpha=0.5)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"\n图已保存：{out}")
    if open_img:
        _open_image(out)


def show_stock(kind, code, name, refresh=False, days=None, bench_code=None, open_img=True):
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
    if open_img:
        _open_image(out)


def main():
    args, days, bench_code, refresh, force_kind, open_img = [], None, None, False, None, True
    i = 1
    while i < len(sys.argv):
        t = sys.argv[i]
        if t == "--days":                       # 近 N 个自然日
            days = int(sys.argv[i + 1]); i += 2
        elif t == "--bench":                    # 换对比基准：指数别名或 6 位指数代码（默认沪深300）
            bench_code = "000300"
            if i + 1 < len(sys.argv):
                nxt = sys.argv[i + 1]
                if nxt in INDEX_ALIAS:
                    bench_code = INDEX_ALIAS[nxt][1]; i += 1
                elif nxt.isdigit() and len(nxt) == 6:
                    bench_code = nxt; i += 1
            i += 1
        elif t == "--refresh":
            refresh = True; i += 1
        elif t == "--no-open":
            open_img = False; i += 1
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
        query = input("请输入股票/指数/基金的名称或代码：").strip().lstrip("﻿")
        if not query:
            return
        d = input("图表区间（天数，直接回车=全部历史，常用 30 / 90 / 365）：").strip().lstrip("﻿")
        if d.isdigit():
            days = int(d)

    result = resolve(query, force_kind)
    if not result:
        return
    kind, code, name = result
    if name == code:  # 数字代码输入时，反查一个好看的名称用于展示
        name = _display_name(kind, code)
    if kind == "fund":
        show_fund(code, name, days, bench_code, open_img)
    else:
        show_stock(kind, code, name, refresh, days, bench_code, open_img)


if __name__ == "__main__":
    main()
