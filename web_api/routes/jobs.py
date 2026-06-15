"""任务接口 — 手动触发 + 执行记录"""
import time
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from db import upsert_rows, start_job_run, finish_job_run, get_engine
from fetcher import fetch_daily, fetch_minute
from config import STOCK_CODES
from ..schemas import df_records

router = APIRouter(tags=["jobs"])


class FetchRequest(BaseModel):
    type: str                       # 'daily' | 'minute'
    codes: Optional[List[str]] = None


@router.post("/jobs/fetch")
def trigger_fetch(req: FetchRequest):
    """手动触发拉取（同步），记 job_runs"""
    if req.type not in ("daily", "minute"):
        return {"error": "type must be 'daily' or 'minute'"}

    codes = req.codes or STOCK_CODES
    fetch_fn = fetch_daily if req.type == "daily" else fetch_minute
    table = "daily_prices" if req.type == "daily" else "minute_prices"
    conflict = (["stock_code", "trade_date"] if req.type == "daily"
                else ["stock_code", "trade_time", "period"])
    job_name = "job_fetch_{}".format(req.type)

    run_id = start_job_run(job_name)
    total = 0
    errors = []
    for code in codes:
        try:
            rows = fetch_fn(code)
            total += upsert_rows(rows, table, conflict)
            time.sleep(0.3)
        except Exception as e:
            errors.append({"code": code, "error": str(e)[:200]})

    status = "ok" if not errors else "failed"
    finish_job_run(run_id, status, rows=total,
                   error=str(errors)[:500] if errors else None)
    return {"run_id": run_id, "type": req.type, "rows": total, "errors": errors}


@router.get("/jobs/runs")
def list_runs(limit: int = Query(20, ge=1, le=100)):
    """最近任务执行记录"""
    e = get_engine()
    df = pd.read_sql(
        text("SELECT id, job_name, started_at, finished_at, status, rows_affected, error "
             "FROM job_runs ORDER BY id DESC LIMIT :lim"),
        e,
        params={"lim": limit},
    )
    return df_records(df)
