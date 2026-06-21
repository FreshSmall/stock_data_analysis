"""
信号扫描编排 — 从股池取股票 → 批量评分 → 入库

设计文档: spec/volume-analysis/2026-06-17-volume-analysis-system-design.md §5.3

依赖: db(股池/写入) + signal_scorer(批量评分)
"""
from datetime import date, datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text

from config import POOL_NAME
from data.db import (
    query_pool_periods, query_pool_stocks, upsert_rows, get_engine,
)
from core.scoring.signal_scorer import score_batch


def _latest_trade_date() -> Optional[date]:
    """取 daily_prices 最新交易日（避免周末/节假日跑空）。"""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT MAX(trade_date) FROM daily_prices")).scalar()
    if row is None:
        return None
    if isinstance(row, datetime):
        return row.date()
    if isinstance(row, str):
        return date.fromisoformat(str(row)[:10])
    return row


def _resolve_signal_date(signal_date) -> date:
    """signal_date 容器统一为 date：None=最新交易日 / date / 'YYYY-MM-DD'。"""
    if signal_date is None:
        d = _latest_trade_date()
        if d is None:
            return date.today()
        return d
    if isinstance(signal_date, date):
        return signal_date
    return date.fromisoformat(str(signal_date)[:10])


def _load_pool_codes() -> list:
    """取最新一期股池股票代码列表（含名称映射）。"""
    periods = query_pool_periods(POOL_NAME)
    if periods.empty:
        return []
    latest_date = periods.iloc[0]["trade_date"]
    stocks = query_pool_stocks(latest_date, POOL_NAME)
    if stocks.empty:
        return []
    return stocks[["stock_code", "stock_name"]].to_dict("records")


def run_daily_signal(signal_date=None, verbose: bool = True) -> dict:
    """盘后扫描流程:
    1. 解析 signal_date（None → 最新交易日）
    2. 从 stock_pool 取最新一期股票列表
    3. score_batch() 批量评分
    4. upsert 入 stock_signal 表
    5. 返回 {'total','scored','skipped','top10'}

    signal_date: None / date / 'YYYY-MM-DD'
    """
    sig_date = _resolve_signal_date(signal_date)
    pool = _load_pool_codes()
    if not pool:
        if verbose:
            print(f"⚠ 股池 {POOL_NAME} 无数据，请先运行 python main.py pool")
        return {"total": 0, "scored": 0, "skipped": 0, "top10": [],
                "signal_date": str(sig_date)}

    codes = [r["stock_code"] for r in pool]
    name_map = {r["stock_code"]: r["stock_name"] for r in pool}
    total = len(codes)
    if verbose:
        print(f"\n📊 信号扫描: signal_date={sig_date} 股池 {total} 只\n")

    # 批量评分
    result = score_batch(codes, sig_date)
    scored = result["scored"]
    skipped = result["skipped"]

    # 补股票名称
    for rec in scored:
        rec["stock_name"] = name_map.get(rec["stock_code"])

    # 入库
    n_written = 0
    if scored:
        n_written = upsert_rows(scored, "stock_signal",
                                ["signal_date", "stock_code"])
        if verbose:
            print(f"\n✅ 入库 stock_signal: {n_written} 条 (date={sig_date})")

    # 输出
    top10 = [
        {"stock_code": r["stock_code"], "stock_name": r["stock_name"],
         "score": r["score"], "label": r["label"], "reason": r["reason"]}
        for r in scored[:10]
    ]
    if verbose:
        _print_summary(total, len(scored), len(skipped), top10, skipped)

    return {
        "total": total, "scored": len(scored), "skipped": len(skipped),
        "top10": top10, "signal_date": str(sig_date),
    }


def _print_summary(total, n_scored, n_skipped, top10, skipped):
    """控制台打印汇总 + Top10。"""
    print(f"\n{'='*70}")
    print(f"📈 扫描完成: 共 {total} 只 | 评分 {n_scored} | 跳过 {n_skipped}")
    # 标签分布
    if top10 or n_scored > 0:
        print(f"{'='*70}")
        print(f"\n🏆 Top 10:")
        for i, r in enumerate(top10, 1):
            print(f"  {i:>2}. {r['stock_code']} {r['stock_name'] or '':<8} "
                  f"{r['score']:>5.1f} [{r['label']}]")
            if r["reason"]:
                print(f"      └ {r['reason'][:80]}")
    # 跳过统计（只打印前 5 条原因样本）
    if skipped:
        print(f"\n⚠ 跳过 {n_skipped} 只（样本）:")
        for s in skipped[:5]:
            print(f"  - {s['stock_code']}: {s['reason']}")
    print(f"{'='*70}\n")
