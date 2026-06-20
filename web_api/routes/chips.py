"""筹码分布接口

端点:
  GET  /stocks/{code}/chip            某股票筹码分布历史（含分布数组）
  GET  /stocks/{code}/chip/latest     某股票最新一条筹码摘要（用于详情卡）
  POST /stocks/{code}/chip/refresh    计算并入库该股票近 N 天筹码数据
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel

from db import query_chip_distribution, query_chip_latest
from ..schemas import df_records

router = APIRouter(tags=["chips"])


@router.get("/stocks/{stock_code}/chip")
def get_chip_history(
    stock_code: str,
    days: int = Query(default=90, ge=1, le=365, description="返回最近 N 天"),
    with_dist: bool = Query(default=False, description="是否返回 distribution 分布数组"),
):
    """读取某股票筹码分布历史，按日期升序。"""
    df = query_chip_distribution(stock_code, days=days, with_dist=with_dist)
    records = df_records(df)
    # trade_date 经 to_json 序列化为 ms 时间戳，统一转为 'YYYY-MM-DD'
    for r in records:
        ts = r.get("trade_date")
        if ts is not None:
            from datetime import datetime
            r["trade_date"] = datetime.utcfromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
    return records


@router.get("/stocks/{stock_code}/chip/latest")
def get_chip_latest(stock_code: str):
    """读取某股票最新一条筹码摘要（不含分布数组）。无数据返回 null。"""
    rec = query_chip_latest(stock_code)
    if rec is None:
        return None
    ts = rec.get("trade_date")
    if ts is not None:
        from datetime import datetime, date
        if isinstance(ts, (int, float)):
            rec["trade_date"] = datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
        elif isinstance(ts, date):
            rec["trade_date"] = ts.strftime("%Y-%m-%d")
        else:
            rec["trade_date"] = str(ts)[:10]
    return rec


class RefreshRequest(BaseModel):
    days: int = 90


@router.post("/stocks/{stock_code}/chip/refresh")
def refresh_chip(stock_code: str, req: RefreshRequest | None = None):
    """计算并入库该股票近 N 天筹码数据（本地 CYQ 算法）。"""
    from chip_fetcher import upsert_chip
    days = req.days if req else 90
    n = upsert_chip(stock_code, days=days)
    return {"stock_code": stock_code, "rows": n, "days": days}
