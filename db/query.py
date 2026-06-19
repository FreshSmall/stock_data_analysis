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


# ===== 信号查询（signal）=====

def query_signals(signal_date, label: str = None,
                  min_score: float = None, limit: int = 100) -> pd.DataFrame:
    """读取某日信号快照，按评分降序。

    参数:
      signal_date: 信号日期（date / 'YYYY-MM-DD' / None=None 时自动取最新一期）
      label:       可选，按标签过滤（强烈关注/值得关注/中性观察/暂不参与）
      min_score:   可选，最低评分阈值
      limit:       返回条数上限（默认 100，0 表示不限）
    """
    engine = get_engine()
    # signal_date 为空时，自动取 stock_signal 最新一期
    if not signal_date:
        latest = pd.read_sql(text(
            "SELECT MAX(signal_date) AS d FROM stock_signal"
        ), engine)
        if latest.empty or latest.iloc[0]["d"] is None:
            return pd.DataFrame()
        signal_date = str(latest.iloc[0]["d"])[:10]

    clauses = ["signal_date = :dt"]
    params = {"dt": signal_date}
    if label:
        clauses.append("label = :label")
        params["label"] = label
    if min_score is not None:
        clauses.append("score >= :ms")
        params["ms"] = min_score
    where = " AND ".join(clauses)
    sql = f"SELECT * FROM stock_signal WHERE {where} ORDER BY score DESC"
    if limit and limit > 0:
        sql += " LIMIT :lim"
        params["lim"] = limit
    return pd.read_sql(text(sql), engine, params=params)


def query_signal_detail(stock_code: str, signal_date=None) -> dict:
    """读取单只股票某日信号详情，返回单行 dict（无数据返回 None）。

    signal_date=None 时取该股票最新一期信号。
    """
    engine = get_engine()
    if signal_date is None:
        sql = text("""
            SELECT * FROM stock_signal
            WHERE stock_code = :code
            ORDER BY signal_date DESC LIMIT 1
        """)
        params = {"code": stock_code}
    else:
        sql = text("""
            SELECT * FROM stock_signal
            WHERE stock_code = :code AND signal_date = :dt
        """)
        params = {"code": stock_code, "dt": signal_date}
    df = pd.read_sql(sql, engine, params=params)
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def query_signal_history(stock_code: str, days: int = 60) -> pd.DataFrame:
    """读取某股票最近 N 天信号历史，按日期升序（用于趋势判断）。"""
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT * FROM stock_signal
        WHERE stock_code = :code
        ORDER BY signal_date DESC
        LIMIT :lim
    """), engine, params={"code": stock_code, "lim": days})
    return df.sort_values("signal_date").reset_index(drop=True)
