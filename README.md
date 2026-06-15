# Stock Data Analysis

从 akshare 拉取 A 股行情数据，存入 MySQL，做技术指标分析。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置数据库（复制 .env.example 并修改）
cp .env.example .env
vim .env

# 3. 初始化数据库
python main.py init

# 4. 拉取日线 + 分钟线 + 分析
python main.py run
```

## 命令列表

| 命令 | 说明 |
|------|------|
| `python main.py init` | 初始化数据库 |
| `python main.py fetch_daily` | 拉取股票池日线数据 |
| `python main.py fetch_daily 600519` | 拉取指定股票日线 |
| `python main.py fetch_minute` | 拉取当天分钟线 |
| `python main.py analyze` | 分析所有股票 |
| `python main.py analyze 600519` | 分析指定股票 |
| `python main.py run` | 一键: 拉取 + 分析 |

## 项目结构

```
stock_data_analysis/
├── .env.example     # 配置模板
├── requirements.txt # 依赖
├── config.py        # 配置加载
├── db/              # 数据库：连接 / 建表 / 查询 / 写入
│   ├── connection.py  # 连接管理
│   ├── schema.py      # 建表
│   ├── query.py       # 查询
│   └── writer.py      # 写入
├── fetcher.py         # akshare 数据拉取
├── analyze.py         # 技术指标分析
├── stock_data_job/    # 定时拉取任务（APScheduler）
│   ├── __main__.py    # 入口：python -m stock_data_job
│   ├── scheduler.py   # 调度器
│   ├── jobs.py        # 任务函数
│   └── trading_cal.py # 交易日判断
├── web_api/           # 后端接口（FastAPI）
│   ├── __main__.py    # 入口：python -m web_api
│   ├── app.py         # FastAPI 应用（含 web_ui 静态托管）
│   ├── schemas.py     # 响应序列化
│   └── routes/        # 路由：stocks / analyze / jobs
├── web_ui/            # 前端看板（原生 HTML + ECharts）
│   ├── index.html     # 单页入口
│   ├── css/main.css
│   ├── js/            # api / charts / app / format（ES module）
│   └── vendor/        # 本地 vendored echarts.min.js
└── main.py            # 入口脚本（手动 CLI）
```

## 分析功能

- 区间统计（最高/最低/均价）
- 均线 MA5/10/20/60
- RSI 超买超卖
- MACD 金叉/死叉
- MA5 × MA20 金叉检测

## 定时任务（stock_data_job）

```bash
# 常驻调度（工作日 15:30 拉分钟线、16:30 拉日线）
python -m stock_data_job

# 调试：立即跑一次
python -m stock_data_job --once daily
python -m stock_data_job --once minute
```

任务执行记录写入 `job_runs` 表。

## Web API（web_api）

```bash
# 启动后端（默认 0.0.0.0:8000，同时托管前端）
python -m web_api

# OpenAPI 文档：http://localhost:8000/docs
```

主要接口：

- `GET /api/stocks` 股票列表
- `GET /api/stocks/{code}/daily` 日线
- `GET /api/stocks/{code}/minute` 分钟线
- `GET /api/analyze/{code}` 技术指标分析
- `POST /api/jobs/fetch` 手动触发拉取（body：`{"type":"daily","codes":["600519"]}`）
- `GET /api/jobs/runs` 任务执行记录

## Web UI（web_ui）

```bash
# 启动 web_api 后，看板自动托管在同一端口根路径
python -m web_api
# 浏览器打开：http://localhost:8000/
```

功能：

- 股票选择 + 刷新
- K 线主图（MA5/10/20/60）+ 成交量 / RSI / MACD 三副图（一个 ECharts 实例多 grid 联动）
- 概览卡片（最新价、区间统计、均线、RSI/MACD、金叉信号）
- 任务面板：一键拉日线 / 分钟线（指定当前股票）+ 最近任务记录

技术：原生 HTML + ES module + 本地 vendored ECharts（`web_ui/vendor/`，离线可用，无构建链）。
