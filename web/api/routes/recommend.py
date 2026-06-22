"""投资推荐接口

端点:
  GET  /recommend/latest?sort=recommend  最新推荐排行（综合/价值/技术/筹码）
  GET  /recommend/runs                    执行历史
  POST /recommend/run                     手动触发推荐计算
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel

from data.db import query_recommend, query_recommend_runs
from ..schemas import df_records

router = APIRouter(tags=["recommend"])


@router.get("/recommend/latest")
def get_latest(sort: str = Query("recommend",
                                  regex="^(recommend|value|technical|chip)$")):
    """最新一批推荐结果，按指定维度排序"""
    df = query_recommend(sort=sort)
    records = df_records(df)
    for r in records:
        if r.get("run_date"):
            r["run_date"] = str(r["run_date"])[:10]
        # reasons 是 JSON 字符串，前端解析
    return records


@router.get("/recommend/runs")
def list_runs(limit: int = Query(20, ge=1, le=100)):
    """推荐执行历史"""
    df = query_recommend_runs(limit=limit)
    records = df_records(df)
    for r in records:
        if r.get("run_date"):
            r["run_date"] = str(r["run_date"])[:10]
    return records


class RunRequest(BaseModel):
    preset: str = "value"
    top_n: int = 100
    skip_fetch: bool = False


@router.post("/recommend/run")
def trigger_run(req: RunRequest | None = None):
    """手动触发推荐计算"""
    from orchestration.recommend_runner import run_recommend
    params = req.model_dump() if req else {}
    result = run_recommend(**params)
    return result
