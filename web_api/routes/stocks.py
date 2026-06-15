"""行情查询接口"""
from fastapi import APIRouter, Query

from db import query_daily, query_minute
from config import STOCK_CODES
from ..schemas import df_records

router = APIRouter(tags=["stocks"])


@router.get("/stocks")
def list_stocks():
    """股票列表"""
    return STOCK_CODES


@router.get("/stocks/{code}/daily")
def get_daily(code: str, limit: int = Query(250, ge=1, le=2000)):
    """日线数据"""
    return df_records(query_daily(code, limit=limit))


@router.get("/stocks/{code}/minute")
def get_minute(code: str, date: str = None, limit: int = Query(1000, ge=1, le=5000)):
    """分钟线数据（date 可选，格式 YYYY-MM-DD）"""
    return df_records(query_minute(code, date_str=date, limit=limit))
