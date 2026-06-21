# Stock Data Analysis

A股行情数据采集、技术分析、股池筛选、成交量信号与量化策略筛选的全栈应用。

从新浪/东财/akshare/baostock 拉取行情数据，存入 MySQL，做技术指标分析，基于量价关系生成每日交易信号，并提供趋势跟踪/突破/回调/动量等量化策略筛选，通过 Web 看板可视化。

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
| `python main.py init` | 初始化数据库（含 8 张表） |
| `python main.py pool` | 股池筛选并入库（全市场行情 + 筛选） |
| `python main.py screen_pool` | 列出可用粗筛预设 |
| `python main.py screen_pool value` | 基础粗筛：价值蓝筹 |
| `python main.py screen_pool growth --top 50` | 成长活跃 前 50 |
| `python main.py screen_pool --custom "total_mv>100,pe>0"` | 自定义条件粗筛 |
| `python main.py fetch_daily` | 拉取股池日线数据（增量，自动判断全量/增量） |
| `python main.py fetch_daily 600519` | 拉取指定股票日线（增量） |
| `python main.py fetch_chip` | 计算全部股票筹码分布（本地 CYQ 算法，近 90 天） |
| `python main.py fetch_chip 600519` | 计算指定股票筹码分布 |
| `python main.py fetch_chip 600519 30` | 指定股票 + 最近 30 天 |
| `python main.py fetch_minute` | 拉取当天分钟线 |
| `python main.py analyze` | 分析所有股票（技术指标） |
| `python main.py analyze 600519` | 分析指定股票 |
| `python main.py run` | 一键: 拉取日线 + 分钟线 + 分析 |
| `python main.py signal` | 扫描股池信号并评分入库 |
| `python main.py backtest` | 回测: 历史扫描 + 收益回填 + 生成报告 |
| `python main.py backfill` | 回填信号收益率（next_5d/20d_return） |
| `python main.py backtest_report` | 仅生成回测报告（基于已有数据） |
| `python main.py screen trend` | 量化策略筛选：趋势跟踪 |
| `python main.py screen breakout 30` | 量化策略筛选：突破信号 Top30 |
| `python main.py screen pullback` | 量化策略筛选：回调买入 |
| `python main.py screen momentum` | 量化策略筛选：动量排名 |

## 项目结构

```
stock_data_analysis/
├── main.py                  # CLI 入口（命令分发）
├── config.py                # 配置加载（DB / 拉取 / 股池 / 信号 / 定时）
├── .env.example             # 配置模板
├── requirements.txt         # 依赖
│
├── core/                    # 🔥 核心业务逻辑（纯算法，无 IO 耦合）
│   ├── indicators/            # 指标计算
│   │   ├── analyze.py           # MA / RSI / MACD / 金叉
│   │   └── volume_engine.py     # 量价分析（量比/OBV/VR/VWAP/异动检测）
│   ├── screeners/             # 筛选器
│   │   ├── pool_screener.py     # 基础粗筛（市值/PE/换手等快照指标）
│   │   └── strategy_screener.py # 策略精筛（趋势/突破/回调/动量）
│   ├── scoring/               # 评分系统
│   │   ├── signal_scorer.py     # 5 维加权 0-100 分 + 筹码调整 ±5
│   │   └── chip_engine.py       # 筹码分布引擎（本地复现 CYQ 算法）
│   └── backtest.py            # 信号回测（历史扫描 + 收益回填 + 胜率统计）
│
├── data/                    # 📥 数据拉取与持久化
│   ├── fetchers/              # 数据源适配
│   │   ├── akshare_fetcher.py  # akshare 主源（增量拉取 + 主备切换）
│   │   └── baostock_fetcher.py # baostock 备源
│   ├── pool_builder.py        # 股池构建（新浪行情 + 东财上市日期/行业）
│   ├── batch_fetcher.py       # 批量拉日线（BaoStock 连接复用 + 增量 + 粗筛联动）
│   ├── chip_fetcher.py        # 筹码数据入库
│   └── db/                    # 数据库层
│       ├── connection.py        # 连接管理
│       ├── schema.py            # 建表（daily/minute/stocks/job_runs/stock_pool/stock_signal/chip_distribution/screen_result）
│       ├── query.py             # 查询（日线/分钟/股池/信号/筹码/漏斗）
│       └── writer.py            # 写入（upsert / job_runs）
│
├── orchestration/          # 🎯 编排层（串联 core + data 完成完整业务流程）
│   ├── signal_runner.py       # 信号扫描编排（股池 → 批量评分 → 入库）
│   └── funnel_runner.py       # 漏斗筛选编排（粗筛 → 拉日线 → 精筛 → 入库）
│
├── web/                    # 🌐 Web 服务
│   ├── api/                   # 后端接口（FastAPI）
│   │   ├── __main__.py          # 入口: python -m web.api
│   │   ├── app.py               # FastAPI 应用（含 web/ui 静态托管）
│   │   ├── schemas.py           # 响应序列化
│   │   └── routes/              # 路由: stocks / analyze / jobs / pools / signals / strategy / chips / funnel
│   └── ui/                    # 前端看板（原生 HTML + ECharts）
│       ├── index.html           # 单页入口（4 个 tab：行情/股池/信号/漏斗）
│       ├── css/main.css         # 样式（深色主题 + 信号配色）
│       ├── js/                  # app/charts/pools/signals/funnel/chips/glossary/api/format
│       └── vendor/              # 本地 vendored echarts.min.js
│
├── scheduler/              # ⏰ 定时任务（APScheduler）
│   ├── __main__.py            # 入口: python -m scheduler
│   ├── scheduler.py           # 调度器（5 个定时任务）
│   ├── jobs.py                # 任务函数（日线/分钟/股池/信号/漏斗）
│   └── trading_cal.py         # 交易日判断
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

### 5. 🔄 分层筛选系统（漏斗式粗筛 → 精筛 → 精细分析）

量化分析采用三层漏斗，避免盲目全量拉取，逐层缩小范围：

```
全市场 4216 只
    │  第 1 层：基础粗筛（stock_pool 快照指标，零网络开销）
    ▼
约 100-1000 只候选（视预设）
    │  第 2 层：拉日线 + 技术指标精筛（MA/RSI/MACD/量比）
    ▼
约 30-80 只精选
    │  第 3 层：筹码分布 + 信号评分
    ▼
约 10-20 只重点关注
```

#### 第 1 层：基础粗筛（`pool_screener.py`）

基于 stock_pool 已有的行情快照（市值/PE/PB/换手率/涨跌幅/行业/上市日期），不需要日线数据：

| 预设 | 条件 | 典型结果 | 适用场景 |
|------|------|---------|---------|
| `value` 价值蓝筹 | 市值>200亿 + PE 5-20 + PB<3 | ~243 只 | 稳健长线 |
| `growth` 成长活跃 | 市值 50-500亿 + PE>0 + 换手 2-10% | ~1046 只 | 中短线波段 |
| `breakout` 低价突破 | 市值>50亿 + 涨>3% + 换手>3% | ~433 只 | 动量突破 |
| `oversold` 超跌反弹 | 市值>100亿 + 跌<-5% + PE>0 | ~74 只 | 抄底候选 |
| `dividend` 高股息防御 | 市值>300亿 + PE<15 + PB<1.5 | ~101 只 | 防御配置 |
| `all_active` 全市场活跃 | 市值>50亿 + 换手>1% | ~2534 只 | 宽口径精筛输入 |

```bash
python main.py screen_pool                    # 列出预设
python main.py screen_pool value --top 50     # 价值蓝筹 Top50
python main.py screen_pool growth             # 成长活跃全部
python main.py screen_pool --custom "total_mv>500,pe<20,turnover>1"  # 自定义
```

#### 第 1.5 层：按粗筛结果拉日线

只对粗筛出的候选股拉日线（而非全市场），大幅减少网络开销：

```bash
python batch_fetch_daily.py --from-screen value     # 仅拉价值蓝筹的日线
python batch_fetch_daily.py --from-screen growth --top 200
```

#### 第 2 层：技术指标精筛（`strategy_screener.py`，见下方第 6 节）

对粗筛结果用 4 种策略精筛，支持 `--from-pool` 直接从粗筛预设切入：

```bash
python main.py screen trend --from-pool value       # 对价值蓝筹做趋势跟踪
python main.py screen breakout --from-pool growth   # 对成长活跃做突破筛选
```

### 6. 🔥 量化策略筛选

针对波段周期（1-4 周）的 4 种选股策略，从全市场筛选符合特定形态的股票。复用现有 MA/RSI/MACD/量价指标，按策略条件精准筛选。

| 策略 | 适用场景 | 核心条件 | 命令 |
|------|---------|---------|------|
| **📈 趋势跟踪** | 顺势持有 | MA20 上行 + 价格站上 MA20 + MACD 多头 + RSI 40-70 | `screen trend` |
| **⚡ 突破信号** | 突破入场 | 收盘价突破 20 日新高 + 量比 > 1.5 + 非过度拉升 | `screen breakout` |
| **🔄 回调买入** | 回调低吸 | 上升趋势 + 近 3 日回调 + 缩量 + 回踩 MA10/MA20 | `screen pullback` |
| **🔥 动量排名** | 强者恒强 | 近 20 日涨幅最强 + RSI 50-70 + 放量 | `screen momentum` |

```bash
# CLI 使用
python main.py screen trend 30      # 趋势跟踪 Top30
python main.py screen breakout 10   # 突破信号 Top10
python main.py screen momentum 20   # 动量排名 Top20

# 浏览器使用
# 信号 Tab → 工具栏策略下拉框 → 选策略 → 排行榜实时切换
```

**策略与信号系统的区别**：
- 信号系统：综合五维评分（0-100 分），适合全面评估
- 策略筛选：按特定交易逻辑精准筛选，适合发现特定形态的股票

### 7. 定时任务

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

### 8. 🎯 筹码分布系统（CYQ）

**数据源说明**：官方接口 `akshare.stock_cyq_em` 依赖的 `push2his.eastmoney.com` 在本机网络环境下被阻断（TLS 握手即被关闭），因此本系统**本地复现**了东方财富的 CYQCalculator 算法，等价于官方接口输出的全部字段，零网络依赖。

**算法原理**（与东财 JS 完全一致）：
1. 取当前价往前 **120 个交易日** K 线
2. 在 `[min(low), max(high)]` 之间按 **150 个价位**分桶
3. 每根 K 线按当日 OHLC 均价为顶点的**三角分布**注入筹码，注入量 = `三角权重 × min(换手率, 1)`；历史筹码按 `(1-换手率)` 衰减（模拟获利盘卖出）
4. 由分布推导：**获利比例** / **平均成本** / **90·70 集中度** / **成本区间**

**衍生字段**：
- `profit_ratio` 获利比例：当前价下方筹码占比（<30% 视为底部）
- `avg_cost` 平均成本：累计 50% 筹码对应价位
- `concentration_90/70` 集中度：`(高-低)/(高+低)`，越小越集中

**评分集成**（独立调整分 ±5，不改变五维权重）：
| 标签 | 条件 | 调整分 |
|------|------|--------|
| 🔒 筹码锁定 | 获利比例 <30% 且 90集中度 <15% | **+5** |
| 📊 筹码收敛 | 获利比例 <50% 且 90集中度 <20% | +2 |
| ⚠️ 获利盘堆积 | 获利比例 >85% | **-5** |
| 筹码分散 | 其它 | 0 |

**CLI 用法**：
```bash
python main.py fetch_chip              # 全部股票，近 90 天
python main.py fetch_chip 600519       # 指定股票
python main.py fetch_chip 600519 30    # 指定股票 + 最近 30 天
```

**前端展示**：信号详情面板内嵌「筹码分布」section，含：
- 🎯 筹码分布横向柱状图（绿=获利盘/红=套牢盘，标注均成本、90 上下沿）
- 📊 获利比例 + 90/70 集中度趋势折线（含 30%/85% 阈值线）
- 📇 最新筹码摘要卡（标签 + 关键指标 + 「重新计算」按钮）

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

**策略**：
- `GET /api/strategies` — 支持的策略列表
- `GET /api/strategy/{name}/screen` — 运行策略筛选（`top_n` 参数）

**筹码分布**：
- `GET /api/stocks/{code}/chip?days=90&with_dist=false` — 筹码历史（`with_dist=true` 返回分布数组）
- `GET /api/stocks/{code}/chip/latest` — 最新一条筹码摘要
- `POST /api/stocks/{code}/chip/refresh` — 计算并入库（`{days: 90}`）

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
- **策略下拉框**：综合评分 / 趋势跟踪 / 突破信号 / 回调买入 / 动量排名（切换后排行榜实时更新）
- 汇总卡片（强烈关注/值得关注/中性观察/暂不参与 计数，策略模式显示命中数）
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
# 全量测试（155 个）
python -m pytest tests/

# 量价引擎测试（31 个）
python -m pytest tests/test_volume_engine.py

# 评分器测试（77 个）
python -m pytest tests/test_signal_scorer.py

# 筹码引擎测试（19 个）
python -m pytest tests/test_chip_engine.py

# 股池粗筛器测试（16 个）
python -m pytest tests/test_pool_screener.py
```

测试策略：核心算法（量价指标计算、评分规则、CYQ 筹码分布、粗筛条件解析）全覆盖离线单测，编排层手动验收。

## 技术栈

- **后端**：Python 3.12 / pandas / SQLAlchemy / FastAPI / APScheduler
- **前端**：原生 HTML + ES module + ECharts（无构建链，离线可用）
- **数据库**：MySQL 8.0
- **数据源**：新浪财经 / 东方财富 / akshare / baostock
