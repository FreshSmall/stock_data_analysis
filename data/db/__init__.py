"""
数据库模块 — 连接 / 建表 / 查询 / 写入

对外统一入口，保持 ``from data.db import get_engine, init_db, query_daily, ...`` 兼容。
子模块按功能拆分：
  - connection: 连接管理
  - schema:     建表 DDL
  - query:      数据查询
  - writer:     数据写入
"""
from .connection import get_engine
from .schema import init_db
from .query import (
    query_daily, query_minute, query_pool_periods, query_pool_stocks,
    query_signals, query_signal_detail, query_signal_history,
    query_chip_distribution, query_chip_latest,
    query_funnel_runs, query_funnel_overview, query_screen_results,
    query_recommend, query_recommend_runs,
    get_last_trade_dates,
)
from .writer import upsert_rows, start_job_run, finish_job_run

__all__ = [
    "get_engine", "init_db",
    "query_daily", "query_minute", "query_pool_periods", "query_pool_stocks",
    "query_signals", "query_signal_detail", "query_signal_history",
    "query_chip_distribution", "query_chip_latest",
    "query_funnel_runs", "query_funnel_overview", "query_screen_results",
    "query_recommend", "query_recommend_runs",
    "get_last_trade_dates",
    "upsert_rows", "start_job_run", "finish_job_run",
]
