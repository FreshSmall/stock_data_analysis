"""
数据查询 — 日线 / 分钟线
"""
import pandas as pd
from sqlalchemy import text

from .connection import get_engine


def query_daily(stock_code: str, limit: int = 250) -> pd.DataFrame:
    """读取日线数据"""
    engine = get_engine()
    df = pd.read_sql(
        text("""
            SELECT * FROM daily_prices
            WHERE stock_code = :code
            ORDER BY trade_date DESC
            LIMIT :limit
        """),
        engine,
        params={"code": stock_code, "limit": limit},
    )
    return df.sort_values("trade_date").reset_index(drop=True)


def query_minute(stock_code: str, date_str: str = None, limit: int = 1000) -> pd.DataFrame:
    """读取分钟线数据"""
    engine = get_engine()
    if date_str:
        sql = """
            SELECT * FROM minute_prices
            WHERE stock_code = :code AND trade_date = :dt
            ORDER BY trade_time ASC
        """
        params = {"code": stock_code, "dt": date_str}
    else:
        sql = """
            SELECT * FROM minute_prices
            WHERE stock_code = :code
            ORDER BY trade_time DESC
            LIMIT :limit
        """
        params = {"code": stock_code, "limit": limit}

    df = pd.read_sql(text(sql), engine, params=params)
    return df.sort_values("trade_time").reset_index(drop=True)


def query_pool_periods(pool_name: str = "default") -> pd.DataFrame:
    """列出该股池所有期次(trade_date + 命中数量),按日期倒序"""
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT trade_date, COUNT(*) AS cnt
        FROM stock_pool
        WHERE pool_name = :name
        GROUP BY trade_date
        ORDER BY trade_date DESC
    """), engine, params={"name": pool_name})
    return df


def query_pool_stocks(trade_date, pool_name: str = "default") -> pd.DataFrame:
    """某期股池全部股票,按总市值降序"""
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT * FROM stock_pool
        WHERE pool_name = :name AND trade_date = :dt
        ORDER BY total_mv DESC
    """), engine, params={"name": pool_name, "dt": trade_date})
    return df
