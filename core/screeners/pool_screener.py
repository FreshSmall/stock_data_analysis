"""
股票池基础粗筛器（pool_screener）

基于 stock_pool 表的行情快照指标（市值/PE/PB/换手率/涨跌幅/行业/上市日期）
做粗筛，不需要日线数据，零网络开销。

定位：量化分层筛选的第 1 层（漏斗最宽端）
  全市场 4216 只 → 粗筛 300-500 只候选 → 精筛(strategy_screener) → 信号评分

预设:
  value       价值蓝筹：大市值 + 低 PE + 低 PB
  growth      成长活跃：中等市值 + 合理 PE + 活跃换手
  breakout    低价突破：当日强势 + 高换手
  oversold    超跌反弹：当日大跌 + 有基本面支撑
  dividend    高股息防御：超大市值 + 极低估值

用法:
  python main.py screen_pool value          # 价值蓝筹
  python main.py screen_pool growth --top 50  # 成长活跃 前50
  python main.py screen_pool --custom "total_mv>100,pe>0,turnover>1"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from sqlalchemy import text

from data.db import get_engine


# ============ §1 预设条件 ============

@dataclass
class Preset:
    """粗筛预设：一组 SQL WHERE 片段 + 描述"""
    name: str           # 英文标识
    label: str          # 中文显示名
    desc: str           # 说明
    where: str          # SQL WHERE 子句（不含 WHERE 关键字）
    order: str = "total_mv DESC"   # 排序
    tags: list = field(default_factory=list)   # 适用场景标签


PRESETS: dict[str, Preset] = {
    "value": Preset(
        name="value", label="价值蓝筹",
        desc="大市值(>200亿) + 低估PE(5-20) + 低PB(<3)，稳健长线",
        where="total_mv > 200 AND pe BETWEEN 5 AND 20 AND pb < 3 AND pe > 0",
        order="pe ASC, total_mv DESC",
        tags=["长线", "稳健"],
    ),
    "growth": Preset(
        name="growth", label="成长活跃",
        desc="中等市值(50-500亿) + 合理PE(>0) + 活跃换手(2-10%)，中短线波段",
        where="total_mv BETWEEN 50 AND 500 AND pe > 0 AND turnover BETWEEN 2 AND 10",
        order="turnover DESC, total_mv DESC",
        tags=["波段", "中短线"],
    ),
    "breakout": Preset(
        name="breakout", label="低价突破",
        desc="市值>50亿 + 当日强势(>3%) + 高换手(>3%)，动量突破候选",
        where="total_mv > 50 AND pct_change > 3 AND turnover > 3",
        order="pct_change DESC, turnover DESC",
        tags=["动量", "突破"],
    ),
    "oversold": Preset(
        name="oversold", label="超跌反弹",
        desc="市值>100亿 + 当日大跌(<-5%) + 有PE支撑(>0)，抄底候选",
        where="total_mv > 100 AND pct_change < -5 AND pe > 0",
        order="pct_change ASC",
        tags=["抄底", "反弹"],
    ),
    "dividend": Preset(
        name="dividend", label="高股息防御",
        desc="超大市值(>300亿) + 极低PE(<15) + 破净或低PB(<1.5)，防御配置",
        where="total_mv > 300 AND pe > 0 AND pe < 15 AND pb < 1.5",
        order="pb ASC, pe ASC",
        tags=["防御", "高股息"],
    ),
    "all_active": Preset(
        name="all_active", label="全市场活跃",
        desc="市值>50亿 + 换手>1%（活跃度基线），适合作为精筛的宽口径输入",
        where="total_mv > 50 AND turnover > 1",
        order="total_mv DESC",
        tags=["宽口径", "精筛输入"],
    ),
}


# ============ §2 筛选执行 ============

def _latest_trade_date() -> str:
    """stock_pool 最新期次的交易日"""
    e = get_engine()
    with e.connect() as c:
        row = c.execute(text("SELECT MAX(trade_date) FROM stock_pool")).fetchone()
        return str(row[0]) if row and row[0] else None


def screen_pool(preset: str = None, custom: str = None,
                top_n: int = None, trade_date: str = None) -> dict:
    """执行粗筛。

    参数（preset / custom 二选一）:
      preset:    预设名（value/growth/breakout/oversold/dividend/all_active）
      custom:    自定义条件，逗号分隔的 key>op<value（如 "total_mv>100,pe>0"）
      top_n:     返回前 N 只
      trade_date: 指定期次（默认最新）

    返回: {'preset', 'label', 'desc', 'trade_date', 'total', 'matched', 'results': list}
    """
    # 确定 WHERE 条件 + 描述
    if custom:
        where = _parse_custom(custom)
        label, desc = "自定义", f"自定义条件: {custom}"
        order = "total_mv DESC"
    elif preset:
        if preset not in PRESETS:
            raise ValueError(f"未知预设: {preset}，可选: {list(PRESETS.keys())}")
        p = PRESETS[preset]
        where, label, desc, order = p.where, p.label, p.desc, p.order
    else:
        raise ValueError("必须指定 preset 或 custom")

    td = trade_date or _latest_trade_date()
    if not td:
        raise RuntimeError("stock_pool 无数据，请先运行 python main.py pool")

    sql = text(f"""
        SELECT stock_code, stock_name, exchange, industry,
               total_mv, circ_mv, pe, pb, pct_change, turnover, list_date
        FROM stock_pool
        WHERE trade_date = :td AND {where}
        ORDER BY {order}
        {'LIMIT :n' if top_n else ''}
    """)

    e = get_engine()
    params = {"td": td}
    if top_n:
        params["n"] = top_n
    with e.connect() as c:
        rows = c.execute(sql, params).fetchall()
        # 全市场总数（同期）
        total = c.execute(
            text("SELECT COUNT(*) FROM stock_pool WHERE trade_date = :td"),
            {"td": td},
        ).scalar()

    results = []
    for r in rows:
        results.append({
            "stock_code": r[0], "stock_name": r[1],
            "exchange": r[2], "industry": r[3],
            "total_mv": float(r[4]) if r[4] else None,
            "circ_mv": float(r[5]) if r[5] else None,
            "pe": float(r[6]) if r[6] else None,
            "pb": float(r[7]) if r[7] else None,
            "pct_change": float(r[8]) if r[8] else None,
            "turnover": float(r[9]) if r[9] else None,
            "list_date": str(r[10])[:10] if r[10] else None,
        })

    return {
        "preset": preset or "custom",
        "label": label,
        "desc": desc,
        "trade_date": str(td)[:10],
        "total": total,
        "matched": len(results),
        "results": results,
    }


def _parse_custom(custom: str) -> str:
    """解析自定义条件 'total_mv>100,pe>0,turnover>1' → SQL WHERE 片段"""
    # 支持的运算符
    parts = []
    for chunk in custom.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        # 匹配 key op value（op 支持 >=, <=, !=, >, <, =）
        import re
        m = re.match(r"(\w+)\s*(>=|<=|!=|>|<|=)\s*([\d.\-]+)", chunk)
        if not m:
            raise ValueError(f"无法解析条件: {chunk}（格式: 字段>数值，如 total_mv>100）")
        col, op, val = m.group(1), m.group(2), m.group(3)
        # 白名单校验列名（防注入）
        allowed = {"total_mv", "circ_mv", "pe", "pb", "pct_change",
                   "turnover", "total_mv", "list_date"}
        if col not in allowed:
            raise ValueError(f"不支持的字段: {col}（可选: {allowed}）")
        if op == "=":
            op = "="
        parts.append(f"{col} {op} {val}")
    if not parts:
        raise ValueError("自定义条件为空")
    return " AND ".join(parts)


def list_codes(preset: str = None, custom: str = None,
               top_n: int = None) -> list[str]:
    """便捷：只返回粗筛后的股票代码列表（供 batch_fetch_daily 等调用）"""
    result = screen_pool(preset=preset, custom=custom, top_n=top_n)
    return [r["stock_code"] for r in result["results"]]


# ============ §3 CLI 展示 ============

def print_screen_result(result: dict):
    """终端友好输出粗筛结果"""
    print(f"\n{'='*60}")
    print(f"📋 粗筛预设: {result['label']}（{result['preset']}）")
    print(f"📝 {result['desc']}")
    print(f"📅 期次: {result['trade_date']}")
    print(f"📊 筛选结果: {result['matched']} / {result['total']} 只")
    print(f"{'='*60}\n")

    if not result["results"]:
        print("  无匹配股票")
        return

    # 表头
    print(f"{'代码':<8} {'名称':<8} {'交易所':<5} {'市值(亿)':>9} {'PE':>7} "
          f"{'PB':>6} {'涨跌%':>7} {'换手%':>7} {'行业'}")
    print("-" * 80)
    for r in result["results"][:50]:  # 终端最多显示 50 行
        name = (r["stock_name"] or "")[:6]
        mv = f"{r['total_mv']:.0f}" if r["total_mv"] else "-"
        pe = f"{r['pe']:.1f}" if r["pe"] else "-"
        pb = f"{r['pb']:.2f}" if r["pb"] else "-"
        pct = f"{r['pct_change']:+.2f}" if r["pct_change"] is not None else "-"
        turn = f"{r['turnover']:.2f}" if r["turnover"] else "-"
        ind = (r["industry"] or "")[:8]
        print(f"{r['stock_code']:<8} {name:<8} {r['exchange'] or '-':<5} "
              f"{mv:>9} {pe:>7} {pb:>6} {pct:>7} {turn:>7} {ind}")

    if result["matched"] > 50:
        print(f"\n  ... 还有 {result['matched'] - 50} 只未显示")

    print(f"\n💡 下一步: python main.py screen trend --from-pool {result['preset']}")
    print(f"         或: python batch_fetch_daily.py --from-screen {result['preset']}\n")
