# 01 接入真实数据源（akshare）

- **状态**：已完成
- **创建**：2026-07-24
- **完成**：2026-07-24

## 目标
用 akshare 拉取真实历史行情，建立本地数据缓存，为后续所有回测提供数据基础。这是整个链路的第一步（数据 → 策略 → 回测 → 对比基准）。

## 验收标准
- [x] `data/` 目录下有贵州茅台（600519）和沪深300（000300）的日线 CSV（另按用户要求加做腾讯 00700.HK 验证）
- [x] 列名统一为 `date, open, high, low, close, volume`，日期升序
- [x] 个股用前复权（`adjust="qfq"`），指数不复权（`adjust=""`）
- [x] 数据区间 2020-01-01 至今，无异常缺失（腾讯 1611 行 / 茅台 1589 行 / 沪深300 1589 行，均符合交易日数量预期；港股与 A 股节假日不同故行数略有差异）
- [x] 画出 K 线肉眼检查：无复权缺口、价格量级合理（PNG 存在 data/ 下）

## 步骤
1. 安装 akshare（`pip install akshare`），确认版本可用 → 1.18.78 ✓
2. 新建 `fetch_data.py`：
   - 拉 A股个股：`ak.stock_zh_a_hist(...)`，港股：`ak.stock_hk_hist(...)`，指数：`ak.index_zh_a_hist(...)`
   - 实际交付为**双源容灾版**：东财接口优先、新浪接口（`stock_zh_a_daily` / `stock_hk_daily` / `stock_zh_index_daily`）兜底
   - 中文列名重命名为统一英文列名，存 `data/`
3. 读取 CSV 画 K 线（复用 wheels.md 的 A股配色样式）→ `plot_kline.py`，人工验证 ✓
4. 拉取+缓存逻辑已沉淀为轮子 `fetch_daily`，收录进 wheels.md ✓

## 交付物
- [fetch_data.py](../fetch_data.py) — `fetch_daily()` + `check_daily()`，双源容灾 + 本地缓存
- [plot_kline.py](../plot_kline.py) — 读缓存 CSV 画 K 线/收盘曲线 PNG
- `data/`：`hk_00700_qfq.csv`（腾讯）、`a_600519_qfq.csv`（茅台）、`idx_000300_raw.csv`（沪深300）+ 各自的 K 线/收盘 PNG

## 坑与笔记
> 已转入 Knowledge/data_sources.md 的条目标 ✅
- ✅ **东财接口在企业网络下被拦截**：东财 kline 接口用带编号的子域名（`33.push2his.eastmoney.com` 等），企业防火墙会间歇性断开连接（`RemoteDisconnected`），主域名偶尔能通但不稳定。教训：①接口容灾是刚需，②Claude 的 Bash 沙箱无外网，联网调试要用 PowerShell。
- ✅ **新浪指数代码前缀**：A 股指数在新浪统一用 `sh` 前缀（`sh000300`），`sz000300` 返回畸形数据报 `KeyError: 'date'`。
- ✅ **前复权可以这样自验**（不依赖外部数据）：qfq 最新收盘价必须等于市价；历史价格应 ≤ 不复权价格。
- 腾讯 2020 至今无长期停牌（1611 行 ≈ 港股预期交易日数）；A 股茅台/沪深300 同为 1589 行，互相印证。
- 数据体检发现腾讯最近三个交易日（2026-07-21~23）从 474 急跌到 445、7-22 放出 6600 万股巨量——真实的急跌，做计划 05 卖出分析时注意。
