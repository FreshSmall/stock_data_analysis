"""成交量分析信号接口

设计文档: spec/volume-analysis/2026-06-17-volume-analysis-system-design.md §6.3
端点:
  GET  /signals                       信号排行榜（按评分降序）
  POST /signals/scan                  手动触发扫描
  GET  /signals/{stock_code}/history  某股票信号历史
  GET  /signals/{stock_code}          某股票信号详情
"""
from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

from db import (
    query_signals, query_signal_detail, query_signal_history,
)
from ..schemas import df_records

router = APIRouter(tags=["signals"])


@router.get("/signals")
def list_signals(
    date: str = Query(default=None, description="信号日期 YYYY-MM-DD，默认最新"),
    label: str = Query(default=None,
                       description="标签过滤：强烈关注/值得关注/中性观察/暂不参与"),
    min_score: float = Query(default=None, description="最低评分阈值"),
    limit: int = Query(default=100, ge=0, le=1000, description="返回条数(0=不限)"),
):
    """读取某日信号排行榜，按评分降序。"""
    return df_records(query_signals(date, label=label, min_score=min_score, limit=limit))


class ScanRequest(BaseModel):
    """扫描请求体（date 可选）"""
    date: str | None = None


@router.post("/signals/scan")
def scan_signals(req: ScanRequest | None = None):
    """手动触发信号扫描并评分入库（同步执行）。

    注意：全股池扫描约 5~10s（已批量预取优化），客户端需保持连接。
    """
    from signal_runner import run_daily_signal
    sig_date = req.date if req else None
    return run_daily_signal(signal_date=sig_date, verbose=False)


@router.get("/signals/{stock_code}/history")
def get_signal_history(stock_code: str, days: int = Query(default=60, ge=1, le=365)):
    """读取某股票最近 N 天信号历史，按日期升序。"""
    return df_records(query_signal_history(stock_code, days=days))


@router.get("/signals/{stock_code}")
def get_signal_detail(stock_code: str, date: str = Query(default=None)):
    """读取某股票某日信号详情。date 为空时取最新一期。"""
    return query_signal_detail(stock_code, signal_date=date)
