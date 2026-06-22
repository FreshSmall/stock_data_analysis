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


def query_chip_distribution(stock_code: str, days: int = 90,
                            with_dist: bool = False) -> pd.DataFrame:
    """读取某股票最近 N 天筹码分布数据，按日期升序。

    参数:
      days:      返回最近 N 天
      with_dist: True 时返回 distribution 列（JSON 字符串），False 时不返回
    """
    engine = get_engine()
    cols = ("trade_date, profit_ratio, avg_cost, cost_90_low, cost_90_high, "
            "concentration_90, cost_70_low, cost_70_high, concentration_70"
            + (", distribution" if with_dist else ""))
    df = pd.read_sql(text(
        f"SELECT {cols} FROM chip_distribution "
        f"WHERE stock_code = :code "
        f"ORDER BY trade_date DESC LIMIT :lim"
    ), engine, params={"code": stock_code, "lim": days})
    return df.sort_values("trade_date").reset_index(drop=True)


def query_chip_latest(stock_code: str) -> dict:
    """读取某股票最新一条筹码摘要（不含 distribution），无数据返回 None。"""
    engine = get_engine()
    df = pd.read_sql(text(
        "SELECT trade_date, profit_ratio, avg_cost, cost_90_low, cost_90_high, "
        "concentration_90, cost_70_low, cost_70_high, concentration_70 "
        "FROM chip_distribution WHERE stock_code = :code "
        "ORDER BY trade_date DESC LIMIT 1"
    ), engine, params={"code": stock_code})
    if df.empty:
        return None
    return df.iloc[0].to_dict()


# ============ 漏斗筛选结果 ============

def query_funnel_runs(limit: int = 20) -> pd.DataFrame:
    """查询漏斗执行历史批次列表（按日期降序）"""
    engine = get_engine()
    df = pd.read_sql(text(
        "SELECT run_id, run_date, preset FROM screen_result "
        "GROUP BY run_id, run_date, preset "
        "ORDER BY run_date DESC, run_id DESC LIMIT :lim"
    ), engine, params={"lim": limit})
    return df


def query_funnel_overview(run_id: str) -> list:
    """查询某批次的漏斗总览：各层的命中数"""
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT layer, preset, strategy,
               COUNT(*) as total,
               SUM(CASE WHEN `match`=1 OR layer=1 THEN 1 ELSE 0 END) as matched
        FROM screen_result
        WHERE run_id = :rid
        GROUP BY layer, preset, strategy
        ORDER BY layer, strategy
    """), engine, params={"rid": run_id})
    return df.to_dict("records")


def query_screen_results(run_id: str, layer: int = None,
                         preset: str = None, strategy: str = None,
                         matched_only: bool = False) -> pd.DataFrame:
    """查询某批次的筛选结果明细"""
    engine = get_engine()
    clauses = ["run_id = :rid"]
    params = {"rid": run_id}
    if layer is not None:
        clauses.append("layer = :layer")
        params["layer"] = layer
    if preset:
        clauses.append("preset = :preset")
        params["preset"] = preset
    if strategy:
        clauses.append("strategy = :strategy")
        params["strategy"] = strategy
    if matched_only:
        clauses.append("(layer = 1 OR `match` = 1)")
    where = " AND ".join(clauses)
    df = pd.read_sql(text(
        f"SELECT * FROM screen_result WHERE {where} "
        f"ORDER BY layer, score DESC, total_mv DESC"
    ), engine, params=params)
    return df


# ============ 投资推荐结果 ============

def query_recommend(sort: str = "recommend") -> pd.DataFrame:
    """查询最新一批推荐结果，按指定维度排序。

    sort: recommend/value/technical/chip
    """
    col_map = {
        "recommend": "recommend_score",
        "value": "value_score",
        "technical": "technical_score",
        "chip": "chip_score",
    }
    sort_col = col_map.get(sort, "recommend_score")
    engine = get_engine()
    df = pd.read_sql(text(f"""
        SELECT * FROM recommend_result
        WHERE run_id = (SELECT MAX(run_id) FROM recommend_result)
        ORDER BY {sort_col} DESC
    """), engine)
    return df


def query_recommend_runs(limit: int = 20) -> pd.DataFrame:
    """推荐执行历史批次"""
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT run_id, run_date,
               COUNT(*) as total,
               SUM(CASE WHEN label='强烈推荐' THEN 1 ELSE 0 END) as strong,
               SUM(CASE WHEN label='值得关注' THEN 1 ELSE 0 END) as watch
        FROM recommend_result
        GROUP BY run_id, run_date
        ORDER BY run_date DESC LIMIT :lim
    """), engine, params={"lim": limit})
    return df


def get_last_trade_dates(stock_codes: list) -> dict:
    """批量查询多只股票的最后交易日，返回 {stock_code: 'YYYY-MM-DD'}。
    无数据的股票不在返回结果中（用于增量拉取判断起点）。"""
    if not stock_codes:
        return {}
    engine = get_engine()
    # 分批避免 SQL IN 列表过长
    out = {}
    batch_size = 500
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ",".join(f":c{j}" for j in range(len(batch)))
        params = {f"c{j}": c for j, c in enumerate(batch)}
        df = pd.read_sql(text(
            f"SELECT stock_code, MAX(trade_date) AS last_date "
            f"FROM daily_prices "
            f"WHERE stock_code IN ({placeholders}) "
            f"GROUP BY stock_code"
        ), engine, params=params)
        for _, row in df.iterrows():
            if row["last_date"] is not None:
                out[row["stock_code"]] = str(row["last_date"])[:10]
    return out
