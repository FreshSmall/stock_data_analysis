"""分析接口"""
from fastapi import APIRouter

from analyze import calc_report

router = APIRouter(tags=["analyze"])


@router.get("/analyze/{code}")
def get_analyze(code: str):
    """技术指标分析报告（结构化）"""
    return calc_report(code)
