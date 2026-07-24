# 01 接入真实数据源（akshare）

- **状态**：进行中
- **创建**：2026-07-24
- **完成**：—

## 目标
用 akshare 拉取真实历史行情，建立本地数据缓存，为后续所有回测提供数据基础。这是整个链路的第一步（数据 → 策略 → 回测 → 对比基准）。

## 验收标准
- [ ] `data/` 目录下有贵州茅台（600519）和沪深300（000300）的日线 CSV
- [ ] 列名统一为 `date, open, high, low, close, volume`，日期升序
- [ ] 个股用前复权（`adjust="qfq"`），指数不复权（`adjust=""`）
- [ ] 数据区间 2020-01-01 至今，无异常缺失（交易日数量合理）
- [ ] 画出 K 线肉眼检查：无复权缺口、价格量级合理

## 步骤
1. 安装 akshare（`pip install akshare`），确认版本可用
2. 新建 `fetch_data.py`：
   - 拉 A股个股：`ak.stock_zh_a_hist(symbol, period="daily", start_date, end_date, adjust="qfq")`
   - 拉指数：`ak.index_zh_a_hist(symbol, period="daily", start_date, end_date)`
   - 中文列名重命名为统一英文列名，存 `data/`
3. 读取 CSV 画 K 线（复用 wheels.md 的 A股配色样式），人工验证
4. 把拉取+缓存逻辑沉淀为轮子，收录进 wheels.md 的 `fetch_stock_data`

## 坑与笔记
> 执行过程中记录，完成后有价值的转入 Knowledge/
- akshare 是网页接口，偶发失败属正常，加重试；数据务必存本地缓存，别每次回测都重新下载
- 沪深300 代码在个股接口和指数接口里不一样（`sh000300` vs `000300`），注意区分
