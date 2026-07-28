# -*- coding: utf-8 -*-
"""
fund_limit.py — 自助工具：查一类基金「能不能买 / 每天最多买多少」

为什么要有这个工具：QDII（纳指/标普/黄金外盘/原油）受**外汇额度**限制常年限购，
额度是国家外汇管理局按**基金公司**给的，所以"换一只基金"经常换不掉限制；而且
限额天天变，任何写在文档里的数字都会过期。落地任何一只基金前先跑一遍这个。

用法：
    python fund_limit.py 纳斯达克          # 关键词模糊查
    python fund_limit.py 黄金 --all        # 连"暂停申购"的一起列出来
    python fund_limit.py 000216            # 也能直接查代码

读法：
    开放申购 / 限大额 = 能买（限大额时看 day_limit 就是每天的上限）
    暂停申购          = 买不了（day_limit 那一栏是失效的历史值，别当真）
    day_limit = 0     = 接口没给限额，多为机构/特定份额（支付宝上通常买不到）
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")

from fetch_data import fetch_fund_purchase

BUYABLE = ("开放申购", "限大额")
HUGE = 1e8          # 接口给个天文数字（如 1000 亿）= 实际上不限购，别当真去相加

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_all = "--all" in sys.argv
    kw = args[0] if args else "纳斯达克"

    df = fetch_fund_purchase()
    hit = df[df["name"].str.contains(kw, na=False) | (df["code"] == kw.zfill(6))]
    hit = hit[~hit["name"].str.contains("美元", na=False)]      # 美元份额走外汇账户，支付宝买不到
    if hit.empty:
        raise SystemExit(f"没找到名字含「{kw}」的场外基金（场内 ETF 不在这张表里）")

    ok = hit[hit["status"].isin(BUYABLE)].sort_values("day_limit", ascending=False)
    no = hit[~hit["status"].isin(BUYABLE)]

    print(f"\n关键词「{kw}」：命中 {len(hit)} 只，其中可申购 {len(ok)} 只、"
          f"暂停申购 {len(no)} 只")
    print(f"{'代码':<8}{'基金简称':<38}{'状态':<6}{'起点':>6}{'日限额':>9}{'申购费':>7}")
    for _, r in (hit if show_all else ok).iterrows():
        lim = "—" if r["day_limit"] == 0 else \
            ("不限" if r["day_limit"] >= HUGE else f"{r['day_limit']:,.0f}")
        print(f"{r['code']:<8}{r['name'][:36]:<38}{r['status']:<6}"
              f"{r['min_buy']:>6.0f}{lim:>9}{r['fee']:>7.2f}")
    if len(ok):
        free = ok[ok["day_limit"] >= HUGE]
        if len(free):        # 有不限购的选择 → 根本不用讨论怎么凑额度
            print(f"\n✓ 有 {len(free)} 只**不限购**（额度栏是天文数字=没设上限），"
                  f"随便挑一只即可，例如 {free.iloc[0]['name']}（{free.iloc[0]['code']}）")
            raise SystemExit(0)
        top = ok.iloc[0]
        # 叠加额度要按**基金公司**去重：同一公司的 A/C/D 份额、乃至同公司的几只同类
        # 基金，用的是同一份外汇额度，把它们相加是自欺。公司名取"关键词前面那一段"。
        firm = ok["name"].str.split(kw).str[0].str.replace(r"[（(].*", "", regex=True)
        per_firm = ok.assign(firm=firm).groupby("firm")["day_limit"].max()
        cap = per_firm[per_firm > 0].sum()
        print(f"\n单只最高额度：{top['name']}（{top['code']}）"
              f"{top['day_limit']:,.0f} 元/日")
        print(f"按公司去重后可叠加：≈ {cap:,.0f} 元/日（{len(per_firm[per_firm > 0])} 家公司："
              + "、".join(f"{f}{v:,.0f}" for f, v in
                          per_firm[per_firm > 0].sort_values(ascending=False).items()) + "）")
        print("  ⚠ 外汇额度按基金公司分配 → 同一公司的 A/C/D 份额共享额度，不能相加；"
              "跨公司才是真叠加，代价是每只基金各自记账、各自算持有期")
    if len(no) and not show_all:
        print(f"（另有 {len(no)} 只暂停申购，加 --all 查看）")
