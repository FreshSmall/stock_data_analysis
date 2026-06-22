"""
筹码分布数据拉取 / 计算 / 入库

数据源: 本地 daily_prices 表 + chip_engine 本地复现 CYQ 算法
       （akshare stock_cyq_em 依赖的 push2his.eastmoney.com 本机网络阻断，
        所以采用本地计算，等价于官方接口字段）

对外接口:
  - fetch_chip(code, days=90) -> list[dict]      计算单只股票近 N 天筹码数据
  - fetch_chip_batch(codes, days) -> dict        批量
  - upsert_chip(code, days=90) -> int            计算 + 入库
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from core.scoring import chip_engine
from data.db import query_daily, upsert_rows


def fetch_chip(stock_code: str, days: int = 90,
               daily_df: pd.DataFrame = None) -> list[dict]:
    """计算某只股票近 N 天的筹码分布，返回可直接 upsert 的 dict 列表。

    daily_df 可选：批量场景下预取 DataFrame 传入避免重复查库。
    """
    df = daily_df if daily_df is not None else query_daily(stock_code, limit=250)
    if df is None or df.empty:
        return []
    rows = chip_engine.compute_chip_distribution(df, last_n=days)
    for r in rows:
        r["stock_code"] = stock_code
    return rows


def upsert_chip(stock_code: str, days: int = 90,
                daily_df: pd.DataFrame = None) -> int:
    """计算并 upsert 入库 chip_distribution，返回写入条数。"""
    rows = fetch_chip(stock_code, days=days, daily_df=daily_df)
    if not rows:
        return 0
    return upsert_rows(
        rows, "chip_distribution",
        conflict_cols=["stock_code", "trade_date"],
    )
