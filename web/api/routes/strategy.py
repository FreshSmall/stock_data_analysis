"""量化策略筛选接口

端点:
  GET  /strategies              支持的策略列表
  GET  /strategy/{name}/screen  运行指定策略筛选
"""
from fastapi import APIRouter, Query

from db import get_engine
from sqlalchemy import text

router = APIRouter(tags=["strategy"])


@router.get("/strategies")
def list_strategies():
    """支持的策略列表"""
    from strategy_screener import STRATEGIES
    return [
        {"key": k, "name": v[0], "desc": _STRATEGY_DESC.get(k, "")}
        for k, v in STRATEGIES.items()
    ]


_STRATEGY_DESC = {
    "trend": "趋势跟踪：MA20上行+价格站上MA20+MACD多头+RSI健康，捕捉上升通道",
    "breakout": "突破信号：收盘价突破20日新高+量比>1.5，突破入场时机",
    "pullback": "回调买入：上升趋势中缩量回踩MA10/MA20，低吸机会",
    "momentum": "动量排名：近20日涨幅最强+RSI强势，强者恒强",
}


@router.get("/strategy/{name}/screen")
def run_strategy_screen(
    name: str,
    top_n: int = Query(50, ge=1, le=500, description="返回前N只"),
):
    """运行指定策略筛选，返回符合条件的股票列表。

    自动从 daily_prices 取有数据的股票进行筛选。
    """
    from strategy_screener import run_screener, STRATEGIES

    if name not in STRATEGIES:
        from fastapi import HTTPException
        raise HTTPException(404, f"未知策略: {name}，可选: {list(STRATEGIES.keys())}")

    # 取有日线数据的股票
    engine = get_engine()
    from pandas import read_sql
    df = read_sql(text("SELECT DISTINCT stock_code FROM daily_prices"), engine)
    codes = df["stock_code"].tolist()

    result = run_screener(name, codes, top_n=top_n)
    return result
