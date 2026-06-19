# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

A股股票数据系统：从公开数据源拉取行情 → 入 MySQL → 技术指标分析 → FastAPI + 原生 ECharts 看板。纯 Python，无前端构建链。

## 常用命令

```bash
# 手动 CLI（main.py）—— init/fetch_daily/fetch_minute/analyze/run/pool
python main.py init                          # 建库建表
python main.py fetch_daily [600519 ...]      # 拉日线，不传参用 .env 的 STOCK_CODES
python main.py analyze [600519]              # 分析报告
python main.py run                           # 一键: init + 日线 + 分钟线 + 分析
python main.py pool                          # 股池筛选入库（当天期次）

# 定时调度（APScheduler，常驻）
python -m stock_data_job                     # 常驻调度（工作日 15:30 分钟线 / 16:30 日线 / 月初股池）
python -m stock_data_job --once daily|minute|pool   # 立即跑一次（调试，不进循环）

# Web（FastAPI，默认 0.0.0.0:8000，同时托管前端）
python -m web_api                            # http://localhost:8000/ 看板，/docs OpenAPI

# 股池筛选 CLI（默认只出 CSV，--db 同时入库）
python a_stock_filter.py --db

# 测试（pytest，全程离线：monkeypatch mock 数据源，无需 DB/网络）
pytest                                       # 全量
pytest tests/test_fetcher_fallback.py        # 单文件
pytest tests/test_fetcher_fallback.py::test_no_fallback_when_primary_ok   # 单用例
```

配置：复制 `.env.example` → `.env`，由 `config.py` 加载（含 `DB_*`、`STOCK_CODES`、各 cron、股池阈值 `POOL_*`）。`DB_URL` 用 `quote_plus` 包裹密码。

## 架构

数据按 **拉取 → 存储 → 分析 → 展示** 单向流动，无回流。

**数据源层（双源 + 回退）**
- `fetcher.py` 主源 akshare（前复权 `qfq`），日线/分钟线均先 `safe_fetch`（3 次重试）；返回空或抛异常时降级到 `baostock_fetcher.py`。**主+备都失败才抛异常，不静默丢数据**——降级决策在 `fetch_daily`/`fetch_minute` 里，新增数据类型请保持这个口径。
- `baostock_fetcher.py` 是真正异源的备用源（与 akshare 不同源）。纯逻辑（代码转换 `_to_bs_code`、行解析 `_parse_*_row`）刻意与 `_query` 网络层分离，所以测试可不联网跑。注意 BaoStock 分钟线仅约 5 个交易日可用。
- `a_stock_filter.py` 股池筛选走**另一套数据源**：新浪 `getHQNodeData(node=hs_a)` 全市场行情+市值、东财 datacenter `RPT_F10_BASIC_ORGINFO` 补上市日期。**不走 akshare/baostock。**

**存储层 `db/`（SQLAlchemy + MySQL，5 张表）**
- 包入口 `db/__init__.py` 暴露 `get_engine / init_db / query_* / upsert_rows / start_job_run / finish_job_run`，外部一律 `from db import ...`，不要直接 import 子模块。
- `writer.upsert_rows` 是通用 `INSERT ... ON DUPLICATE KEY UPDATE`，按 `conflict_cols`（唯一键列）区分「不参与更新」的列。新增表写入时确认传对 `conflict_cols`。
- 建表 DDL 在 `schema.py`（`daily_prices / minute_prices / stocks / job_runs / stock_pool`）。

**分析层** `analyze.py`：pandas 实现 MA5/10/20/60、RSI、MACD、MA5×MA20 金叉，从 `db.query_daily` 取数。

**编排层**（两条入口，复用同一批 fetcher+db）
- `main.py`：手动一次性 CLI。
- `stock_data_job/`：APScheduler 常驻。`jobs._run` 统一做「交易日判断 → 遍历股票池 → upsert → 记 `job_runs`」；`trading_cal.py` 用 akshare 交易日历并进程内缓存；时区固定 `Asia/Shanghai`。

**展示层**
- `web_api/`：FastAPI，路由按域拆在 `routes/`（stocks/analyze/jobs/pools），全部挂 `/api` 前缀。
- `web_ui/`：原生 HTML + ES module + 本地 vendored ECharts（`web_ui/vendor/`，离线可用）。
- **静态托管顺序有坑**：`app.py` 必须先 `include_router` 再 `app.mount("/", ...)`，否则 `/api/*` 会被静态文件拦截。

## 关键约定（易踩坑）

- **网络代理**：本机系统代理 `127.0.0.1:7897` 对行情数据源转发不稳定，东财 push2 不可用。`a_stock_filter.py` 所有请求强制 `proxies={"http": None, "https": None}` 直连并自带重试。新写直连行情源脚本时沿用此模式。
- **股票代码格式**：库内统一 6 位纯数字代码；BaoStock 需带交易所前缀（`sh.`/`sz.`），由 `_to_bs_code` 转换，仅支持沪/深主板（6/0/3 开头）。
- **复权口径**：akshare `qfq` 与 BaoStock `adjustflag=2` 均为前复权，两源混用不会错位——改其中一个时要保持一致。
- **幂等**：`run_pool` 同期重跑按 `(pool_name, trade_date, stock_code)` upsert 覆盖；日线/分钟线按各自唯一键幂等。
- **代码风格**：类型注解混用 `list[dict]`（3.9+ 内置泛型）与 `typing.List/Dict/Optional`，沿用各文件现有写法即可。

## 设计文档

历史设计与方案存于 `spec/`（按需求分子目录：`data-source-fallback`、`service-expansion`、`db-module`、`stock-pool`），改对应模块前可先查相关 spec。
