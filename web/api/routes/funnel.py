"""漏斗筛选接口

端点:
  GET  /funnel/runs                    执行历史列表
  GET  /funnel/{run_id}/overview       某批次漏斗总览（各层命中数）
  GET  /funnel/{run_id}                某批次某层股票明细
  POST /funnel/run                     手动触发漏斗
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from db import query_funnel_runs, query_funnel_overview, query_screen_results, get_engine
from ..schemas import df_records

router = APIRouter(tags=["funnel"])


@router.get("/funnel/runs")
def list_runs(limit: int = Query(20, ge=1, le=100)):
    """漏斗执行历史列表"""
    df = query_funnel_runs(limit=limit)
    records = df_records(df)
    # 补充各层命中数
    engine = get_engine()
    for r in records:
        rid = r["run_id"]
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT layer, strategy, COUNT(*) as total, "
                "SUM(CASE WHEN layer=1 OR `match`=1 THEN 1 ELSE 0 END) as matched "
                "FROM screen_result WHERE run_id=:rid "
                "GROUP BY layer, strategy ORDER BY layer, strategy"
            ), {"rid": rid}).fetchall()
        r["layers"] = [
            {"layer": row[0], "strategy": row[1],
             "total": row[2], "matched": row[3]}
            for row in rows
        ]
        if r.get("run_date"):
            r["run_date"] = str(r["run_date"])[:10]
    return records


@router.get("/funnel/{run_id}/overview")
def get_overview(run_id: str):
    """某批次漏斗总览"""
    return query_funnel_overview(run_id)


@router.get("/funnel/{run_id}")
def get_results(
    run_id: str,
    layer: int = Query(None, description="1=粗筛 2=精筛"),
    strategy: str = Query(None, description="精筛策略(trend/breakout/...)"),
    matched_only: bool = Query(False, description="仅返回命中的"),
):
    """某批次某层股票明细"""
    df = query_screen_results(run_id, layer=layer, strategy=strategy,
                              matched_only=matched_only)
    records = df_records(df)
    for r in records:
        if r.get("run_date"):
            r["run_date"] = str(r["run_date"])[:10]
    return records


class RunRequest(BaseModel):
    preset: str = "value"
    strategies: list = None
    top_n: int = 50
    skip_fetch: bool = False


@router.post("/funnel/run")
def trigger_run(req: RunRequest | None = None):
    """手动触发漏斗筛选"""
    from funnel_runner import run_funnel
    params = req.model_dump() if req else {}
    result = run_funnel(**params)
    return result
