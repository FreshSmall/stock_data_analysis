# Stock Data Analysis

A股行情数据采集、技术分析、股池筛选与成交量信号系统的全栈应用。

从新浪/东财/akshare/baostock 拉取行情数据，存入 MySQL，做技术指标分析，并基于量价关系生成每日交易信号，通过 Web 看板可视化。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据库（复制 .env.example 并修改）
cp .env.example .env
vim .env

# 3. 初始化数据库
python main.py init

# 4. 股池筛选（拉取全市场行情 + 筛选入库）
python main.py pool

# 5. 拉取日线 + 分钟线 + 分析
python main.py run

# 6. 信号扫描（对股池股票评分）
python main.py signal

# 7. 启动 Web 服务
python -m web_api
# 浏览器打开 http://localhost:8000/
```

## 命令列表

| 命令 | 说明 |
|------|------|
| `python main.py init` | 初始化数据库（含 7 张表） |
| `python main.py pool` | 股池筛选并入库（全市场行情 + 筛选） |
| `python main.py fetch_daily` | 拉取股池日线数据（增量，自动判断全量/增量） |
| `python main.py fetch_daily 600519` | 拉取指定股票日线（增量） |
| `python main.py fetch_minute` | 拉取当天分钟线 |
| `python main.py analyze` | 分析所有股票（技术指标） |
| `python main.py analyze 600519` | 分析指定股票 |
| `python main.py run` | 一键: 拉取日线 + 分钟线 + 分析 |
| `python main.py signal` | 扫描股池信号并评分入库 |
| `python main.py backtest` | 回测: 历史扫描 + 收益回填 + 生成报告 |
| `python main.py backfill` | 回填信号收益率（next_5d/20d_return） |
| `python main.py backtest_report` | 仅生成回测报告（基于已有数据） |

## 项目结构

```
stock_data_analysis/
├── .env.example          # 配置模板
├── requirements.txt      # 依赖
├── config.py             # 配项加载（DB / 拉取 / 股池 / 信号 / 定时）
│
├── db/                   # 数据库层
│   ├── connection.py       # 连接管理
│   ├── schema.py           # 建表（daily/minute/stocks/job_runs/stock_pool/stock_signal/stock_signal_log）
│   ├── query.py            # 查询（日线/分钟/股池/信号）
│   └── writer.py           # 写入（upsert / job_runs）
│
├── fetcher.py            # akshare 数据拉取（增量拉取 + 主备切换）
├── baostock_fetcher.py   # baostock 数据拉取（备选数据源，支持增量）
├── a_stock_filter.py     # 股池筛选器（新浪行情 + 东财上市日期/行业）
├── analyze.py            # 技术指标分析（MA/RSI/MACD/金叉）
│
├── volume_engine.py      # 🔥 量价分析引擎（量比/OBV/VR/VWAP/异动检测）
├── signal_scorer.py      # 🔥 综合评分器（5 维加权 0-100 分 + 标签 + 理由）
├── signal_runner.py      # 🔥 信号扫描编排（股池 → 批量评分 → 入库）
├── signal_backtest.py    # 🔥 信号回测（历史扫描 + 收益回填 + 胜率统计）
│
├── stock_data_job/       # 定时任务（APScheduler）
│   ├── __main__.py         # 入口: python -m stock_data_job
│   ├── scheduler.py        # 调度器（4 个定时任务）
│   ├── jobs.py             # 任务函数（日线/分钟/股池/信号）
│   └── trading_cal.py      # 交易日判断
│
├── web_api/              # 后端接口（FastAPI）
│   ├── __main__.py         # 入口: python -m web_api
│   ├── app.py              # FastAPI 应用（含 web_ui 静态托管）
│   ├── schemas.py          # 响应序列化
│   └── routes/             # 路由: stocks / analyze / jobs / pools / signals
│
├── web_ui/               # 前端看板（原生 HTML + ECharts）
│   ├── index.html          # 单页入口（3 个 tab）
│   ├── css/main.css        # 样式（深色主题 + 信号配色）
│   ├── js/
│   │   ├── app.js            # 主逻辑（行情 tab + 股票筛选器）
│   │   ├── charts.js         # K线图渲染
│   │   ├── pools.js          # 股池 tab
│   │   ├── signals.js        # 信号 tab（排行榜 + 详情面板）
│   │   ├── glossary.js       # 术语字典 + tooltip 组件
│   │   ├── api.js            # API 封装
│   │   └── format.js         # 格式化工具
│   └── vendor/               # 本地 vendored echarts.min.js
│
├── tests/                # 单元测试
│   ├── test_volume_engine.py    # 量价引擎 31 测试
│   └── test_signal_scorer.py    # 评分器 77 测试
│
├── spec/                 # 设计文档
│   └── volume-analysis/    # 信号系统设计 + 实施计划 + 回测报告
│
└── main.py               # 入口脚本
```

## 功能模块

### 1. 数据采集

| 数据源 | 内容 | 接口 |
|--------|------|------|
| 新浪财经 | 全市场行情（价/量/市值/换手/PE/PB） | `getHQNodeData(node=hs_a)` |
| 东方财富 | 上市日期 + 行业分类 + B 股标识 | `RPT_F10_BASIC_ORGINFO` |
| akshare | 日线 / 分钟线 | baostock 回退 |
| baostock | 日线（备选数据源） | akshare 失败时自动切换 |

**日线增量拉取**：`fetch_daily` 默认增量拉取——先查每只股票的最后交易日，仅拉取之后的新数据；无历史数据的股票全量回溯 `HISTORY_DAYS`（默认 365 天）。日常更新从全量 ~79 万条降至 ~3 千条，减少 99%+ 请求量。

```bash
python main.py fetch_daily           # 增量拉取（自动判断全量/增量）
python main.py fetch_daily 600519    # 指定股票增量拉取
```

### 2. 股池筛选

从全市场 ~5200 只 A 股中筛选出符合条件的股票池（默认 ~3250 只）。

**筛选条件**（阈值可在 `.env` 调整）：

| 条件 | 阈值 | 配置项 |
|------|------|--------|
| 非 ST / 非退市 | 名称判断 | 硬编码 |
| 总市值 > 30 亿 | 30 | `POOL_MIN_TOTAL_MV` |
| 流通市值 > 15 亿 | 15 | `POOL_MIN_CIRC_MV` |
| 上市满 1 年 | 365 天 | `POOL_MIN_LISTING_DAYS` |

```bash
python main.py pool    # 筛选并入库
```

### 3. 技术指标分析

- 区间统计（最高/最低/均价/日均涨跌）
- 均线 MA5 / MA10 / MA20 / MA60
- RSI（超买超卖判断）
- MACD（DIF / DEA / 柱状图 / 金叉死叉）
- MA5 × MA20 金叉检测

### 4. 🔥 成交量信号系统

基于量价关系的综合评分系统，每日盘后扫描全股池，生成「值得关注股票清单」。

**五维评分模型**（满分 100）：

| 维度 | 满分 | 核心指标 |
|------|------|---------|
| 量价配合 | 30 | 量比 / MAVOL 金叉 / 量价同向 / 放量突破 / 缩量回踩 |
| 趋势方向 | 25 | MA 排列 / MA5 斜率 / MACD 柱 / 均线乖离 |
| 动量信号 | 20 | RSI / MACD 金叉 / MA 金叉 / VR |
| 异动检测 | 15 | 成交量 Z-Score / 换手率突增 / 尾盘集中度 |
| 分时确认 | 10 | VWAP 偏离 / 小时段分布 / 分时连续性 |

**标签映射**：
- 🟢 **80-100 强烈关注**：多维度共振，重点关注
- 🟡 **65-79 值得关注**：部分维度突出
- ⚪ **50-64 中性观察**：信号不明确
- ⚫ **0-49 暂不参与**：无有效信号

```bash
python main.py signal          # 扫描评分
python main.py backtest        # 回测验证
python main.py backtest_report # 生成报告
```

### 5. 定时任务

```bash
# 常驻调度（4 个定时任务）
python -m stock_data_job

# 调试：立即跑一次
python -m stock_data_job --once daily
python -m stock_data_job --once minute
python -m stock_data_job --once pool
python -m stock_data_job --once signal
```

**调度时间表**（工作日）：

| 时间 | 任务 | 说明 |
|------|------|------|
| 15:30 | 分钟线拉取 | 当天分时数据 |
| 16:30 | 日线拉取 | 日 K 数据 |
| 17:00 | 信号扫描 | 盘后评分入库 |
| 每月 1 日 09:00 | 股池筛选 | 更新股票池 |

任务执行记录写入 `job_runs` 表，可通过 API 查询。

## Web API

```bash
python -m web_api
# OpenAPI 文档: http://localhost:8000/docs
```

### 接口列表

**股票**：
- `GET /api/stocks` — 股票列表（code + name）
- `GET /api/stocks/list` — 全量股票详情（含市值/PE/PB/行业，用于筛选）
- `GET /api/stocks/{code}/info` — 单只股票详情
- `GET /api/stocks/{code}/daily` — 日线数据
- `GET /api/stocks/{code}/minute` — 分钟线数据
- `GET /api/analyze/{code}` — 技术指标分析

**股池**：
- `GET /api/pools` — 股池期次列表
- `GET /api/pools/{trade_date}/stocks` — 某期股池股票
- `POST /api/pools/refresh` — 手动触发股池筛选

**信号**：
- `GET /api/signals` — 信号排行榜（`date` / `label` / `min_score` / `limit`）
- `GET /api/signals/{code}` — 单只股票信号详情
- `GET /api/signals/{code}/history` — 信号历史
- `POST /api/signals/scan` — 手动触发信号扫描

**任务**：
- `POST /api/jobs/fetch` — 手动触发数据拉取
- `GET /api/jobs/runs` — 任务执行记录

## Web UI

```bash
python -m web_api
# 浏览器打开: http://localhost:8000/
```

### 三个功能 Tab

**📊 行情 Tab**
- K 线主图（MA5/10/20/60）+ 成交量 / RSI / MACD 三副图联动
- 概览卡片（最新价、区间统计、均线、RSI/MACD、金叉信号）
- 右侧概览栏指标带术语注释（hover ? 查看含义）
- 顶部栏：股票名称 + 交易所标签 + 行业标签 + 市值 + PE/PB

**📋 股池 Tab**
- 股池期次选择
- 股票表格（代码/名称/板块/市值/PE/PB/涨跌幅/换手率）
- 手动刷新股池

**✨ 信号 Tab**
- 筛选工具栏（日期 / 标签 / 最低分滑块 / 搜索 / 扫描按钮）
- 汇总卡片（强烈关注/值得关注/中性观察/暂不参与 计数）
- 排行榜表格（评分进度条 + 量比/量价趋势/MACD 配色 + 列头排序）
- **点击行展开详情面板**：
  - 评分仪表盘 Gauge（分段色）
  - 五维雷达图（量价/趋势/动量/异动/分时）
  - K 线图 + 成交量副图 + 信号日标记
  - 分时分布 + 尾盘集中度
  - 信号理由（自然语言）+ 近期历史趋势

### 股票筛选器

顶部「⚙ 筛选」按钮，支持 7 个维度实时筛选：

| 维度 | 示例选项 |
|------|---------|
| 交易所 | 沪市 / 深市 / 北交所 |
| 板块 | 制造业 / 金融业 / 信息技术 等 19 个行业 |
| 总市值 | 小盘<100 / 中盘500-1000 / 大盘>1000 亿 |
| PE | 低估<15 / 合理15-25 / 高估>40 |
| PB | 破净<1 / 合理1-3 / 高估>5 |
| 涨跌幅 | 强势>5% / 上涨0-5% / 下跌 / 弱势<-5% |
| 换手率 | 低迷<1% / 正常1-5% / 活跃>5% |

筛选结果以表格展示，点击行可加载该股票行情。

### 术语注释系统

所有专业术语旁带蓝色 ? 圆圈，hover 显示释义 + 数值参考：
- 覆盖 40+ 术语（MA/RSI/MACD/PE/PB/量比/VWAP/OBV/VR 等）
- 三个 Tab 均有注释
- 支持键盘访问（Tab 键聚焦）

## 配置说明

所有配置通过 `.env` 环境变量管理（参考 `.env.example`）：

```bash
# 数据库
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=stock_data

# 数据拉取
HISTORY_DAYS=365              # 首次拉取/全量回溯天数（增量模式仅对新股票生效）

# 股池筛选阈值
POOL_MIN_TOTAL_MV=30        # 最低总市值（亿）
POOL_MIN_CIRC_MV=15         # 最低流通市值（亿）
POOL_MIN_LISTING_DAYS=365   # 最低上市天数

# 信号系统
SIGNAL_CRON=0 17 * * 1-5    # 盘后扫描时间
SIGNAL_MIN_SCORE=0          # 最低入库评分
SIGNAL_W_VOL_PRICE=0.30     # 量价权重
SIGNAL_W_TREND=0.25         # 趋势权重
SIGNAL_W_MOMENTUM=0.20      # 动量权重
SIGNAL_W_ANOMALY=0.15       # 异动权重
SIGNAL_W_INTRADAY=0.10      # 分时权重

# 定时任务
JOB_DAILY_CRON=0 16 * * 1-5
JOB_MINUTE_CRON=30 15 * * 1-5
POOL_CRON=0 9 1 * *
```

## 测试

```bash
# 全量测试
python -m pytest tests/

# 量价引擎测试（31 个）
python -m pytest tests/test_volume_engine.py

# 评分器测试（77 个）
python -m pytest tests/test_signal_scorer.py
```

测试策略：核心算法（量价指标计算、评分规则）全覆盖离线单测，编排层手动验收。

## 技术栈

- **后端**：Python 3.12 / pandas / SQLAlchemy / FastAPI / APScheduler
- **前端**：原生 HTML + ES module + ECharts（无构建链，离线可用）
- **数据库**：MySQL 8.0
- **数据源**：新浪财经 / 东方财富 / akshare / baostock
