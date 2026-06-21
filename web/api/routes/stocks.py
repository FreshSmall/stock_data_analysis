"""行情查询接口"""
from fastapi import APIRouter, Query
from sqlalchemy import text

from db import query_daily, query_minute, get_engine
from config import STOCK_CODES
from ..schemas import df_records

router = APIRouter(tags=["stocks"])


@router.get("/stocks")
def list_stocks():
    """股票列表（含名称）。优先 stocks 表，回退到 stock_pool 最新一期。"""
    engine = get_engine()
    from pandas import read_sql
    # 先查 stocks 表
    df = read_sql(text("SELECT stock_code, stock_name FROM stocks ORDER BY stock_code"), engine)
    if not df.empty:
        return df.to_dict("records")
    # 回退：stock_pool 最新一期的股票（含名称）
    df = read_sql(text("""
        SELECT DISTINCT p.stock_code, p.stock_name
        FROM stock_pool p
        INNER JOIN (
            SELECT MAX(trade_date) AS max_date FROM stock_pool
        ) m ON p.trade_date = m.max_date
        ORDER BY p.stock_code
    """), engine)
    if not df.empty:
        return df.to_dict("records")
    # 最终回退：有日线数据的股票
    df = read_sql(text(
        "SELECT DISTINCT stock_code, NULL AS stock_name FROM daily_prices ORDER BY stock_code"
    ), engine)
    return df.to_dict("records")


@router.get("/stocks/list")
def list_stocks_with_detail():
    """全量股票详情（取 stock_pool 最新一期），用于前端筛选。
    返回字段：stock_code/stock_name/exchange/industry/total_mv/circ_mv/pe/pb/pct_change/turnover
    """
    engine = get_engine()
    from pandas import read_sql
    df = read_sql(text("""
        SELECT stock_code, stock_name, exchange, industry, total_mv, circ_mv,
               pe, pb, pct_change, turnover
        FROM stock_pool
        WHERE trade_date = (SELECT MAX(trade_date) FROM stock_pool)
        ORDER BY total_mv DESC
    """), engine)
    # 数值列转 float（DECIMAL 序列化会变字符串，统一为 number）
    for col in ["total_mv", "circ_mv", "pe", "pb", "pct_change", "turnover"]:
        if col in df.columns:
            df[col] = df[col].astype(float)
    # 行业简化映射
    df["industry"] = df["industry"].map(_simplify_industry)
    return df.to_dict("records")


# 证监会行业大类 → 简称映射
_INDUSTRY_MAP = {
    "制造业": "制造业",
    "信息传输、软件和信息技术服务业": "信息技术",
    "批发和零售业": "批发零售",
    "电力、热力、燃气及水生产和供应业": "公用事业",
    "金融业": "金融业",
    "交通运输、仓储和邮政业": "交运仓储",
    "采矿业": "采矿业",
    "科学研究和技术服务业": "科研服务",
    "房地产业": "房地产",
    "建筑业": "建筑业",
    "水利、环境和公共设施管理业": "环保",
    "租赁和商务服务业": "租赁商务",
    "文化、体育和娱乐业": "文娱",
    "农、林、牧、渔业": "农林牧渔",
    "卫生和社会工作": "医疗卫生",
    "住宿和餐饮业": "住宿餐饮",
    "综合": "综合",
    "教育": "教育",
    "居民服务、修理和其他服务业": "居民服务",
}


def _simplify_industry(raw):
    """原始行业名 → 简称；未匹配则取首 4 字"""
    if not raw:
        return None
    return _INDUSTRY_MAP.get(raw, raw[:4])


@router.get("/stocks/{code}/info")
def get_stock_info(code: str):
    """股票详情：关联 stock_pool 最新一期，返回名称/交易所/市值/估值等。
    若不在股池则返回 stocks 表的基础信息。"""
    engine = get_engine()
    from pandas import read_sql
    # 优先取股池最新一期（有市值/估值）
    df = read_sql(text("""
        SELECT p.stock_code, p.stock_name, p.exchange, p.industry, p.close, p.pct_change,
               p.total_mv, p.circ_mv, p.turnover, p.pe, p.pb, p.list_date
        FROM stock_pool p
        WHERE p.stock_code = :code
        ORDER BY p.trade_date DESC LIMIT 1
    """), engine, params={"code": code})
    if not df.empty:
        d = df.iloc[0].to_dict()
        d["industry"] = _simplify_industry(d.get("industry"))
        return d
    # 回退到 stocks 表
    df2 = read_sql(text(
        "SELECT stock_code, stock_name FROM stocks WHERE stock_code = :code"
    ), engine, params={"code": code})
    if not df2.empty:
        return df2.iloc[0].to_dict()
    return {"stock_code": code, "stock_name": None}


@router.get("/stocks/{code}/daily")
def get_daily(code: str, limit: int = Query(250, ge=1, le=2000)):
    """日线数据"""
    return df_records(query_daily(code, limit=limit))


@router.get("/stocks/{code}/minute")
def get_minute(code: str, date: str = None, limit: int = Query(1000, ge=1, le=5000)):
    """分钟线数据（date 可选，格式 YYYY-MM-DD）"""
    return df_records(query_minute(code, date_str=date, limit=limit))
