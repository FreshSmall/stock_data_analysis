"""股池查询/刷新接口"""
from fastapi import APIRouter, Query

from db import query_pool_periods, query_pool_stocks
from config import POOL_NAME
from ..schemas import df_records

router = APIRouter(tags=["pools"])


@router.get("/pools")
def list_pool_periods(pool_name: str = Query(default=None)):
    """列出股池所有期次(trade_date + 命中数量)，按日期倒序"""
    name = pool_name or POOL_NAME
    return df_records(query_pool_periods(name))


@router.get("/pools/{trade_date}/stocks")
def get_pool_stocks(trade_date: str, pool_name: str = Query(default=None)):
    """某期股池全部股票，按总市值降序"""
    name = pool_name or POOL_NAME
    return df_records(query_pool_stocks(trade_date, name))


@router.post("/pools/refresh")
def refresh_pool(pool_name: str = Query(default=None)):
    """手动触发股池筛选入库（以今天为期次）。
    注意：同步执行全市场筛选，约 1~2 分钟，客户端需保持长连接。"""
    from a_stock_filter import run_pool
    name = pool_name or POOL_NAME
    n = run_pool(pool_name=name)
    return {"pool_name": name, "count": n}
