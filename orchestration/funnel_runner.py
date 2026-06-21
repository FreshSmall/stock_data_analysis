"""
漏斗筛选编排器（funnel_runner）

串联三层漏斗：粗筛(pool_screener) → 拉日线(batch_fetch_daily) → 精筛(strategy_screener)
结果持久化到 screen_result 表。

用法:
  python main.py funnel                    # 默认: value + [trend,breakout,momentum]
  python main.py funnel growth             # 指定预设
  python main.py funnel value trend        # 指定预设+策略
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from data.db import upsert_rows, start_job_run, finish_job_run, get_engine
from sqlalchemy import text


def run_funnel(preset: str = "value",
               strategies: list = None,
               top_n: int = 50,
               skip_fetch: bool = False) -> dict:
    """执行完整漏斗筛选。

    参数:
      preset:      粗筛预设 (value/growth/breakout/oversold/dividend/all_active)
      strategies:  精筛策略列表，默认 ["trend", "breakout", "momentum"]
      top_n:       精筛每策略返回前 N 只
      skip_fetch:  跳过日线拉取（测试用，假设已有日线）

    返回: {run_id, preset, run_date, layers, final_codes}
    """
    from core.screeners.pool_screener import screen_pool, PRESETS
    from core.screeners.strategy_screener import run_screener, STRATEGIES

    if strategies is None:
        strategies = ["trend", "breakout", "momentum"]

    if preset not in PRESETS:
        raise ValueError(f"未知预设: {preset}，可选: {list(PRESETS.keys())}")

    today = date.today().isoformat()
    run_id = f"{today}-{preset}"
    layers = []

    run_db_id = start_job_run("job_funnel")

    # ===== 第 1 层：粗筛 =====
    print(f"\n{'='*60}")
    print(f"🎯 漏斗筛选开始 | 预设: {PRESETS[preset].label}({preset}) | run_id: {run_id}")
    print(f"{'='*60}\n")

    result_l1 = screen_pool(preset=preset)
    codes_l1 = [r["stock_code"] for r in result_l1["results"]]
    layer1 = {
        "layer": 1, "name": f"粗筛·{PRESETS[preset].label}",
        "preset": preset, "strategy": None,
        "total": result_l1["total"], "matched": len(codes_l1),
    }
    layers.append(layer1)
    print(f"  第 1 层 粗筛: {layer1['total']} → {layer1['matched']} 只\n")

    # 入库 layer 1
    rows_l1 = []
    for r in result_l1["results"]:
        rows_l1.append({
            "run_id": run_id, "run_date": today, "layer": 1,
            "preset": preset, "strategy": None,
            "stock_code": r["stock_code"], "stock_name": r.get("stock_name"),
            "exchange": r.get("exchange"),
            "total_mv": r.get("total_mv"), "pe": r.get("pe"),
            "pb": r.get("pb"), "turnover": r.get("turnover"),
            "pct_change": r.get("pct_change"), "industry": r.get("industry"),
        })
    if rows_l1:
        n1 = upsert_rows(rows_l1, "screen_result",
                         conflict_cols=["run_id", "layer", "strategy", "stock_code"])
        print(f"  入库 layer1: {n1} 条")

    # ===== 第 1.5 层：增量拉日线 =====
    if not skip_fetch:
        from data.batch_fetcher import fetch_batch
        print(f"\n  📥 增量拉取日线（跳过已有）…")
        try:
            fetch_batch(codes_l1, days=365)
        except Exception as e:
            print(f"  ⚠️ 日线拉取出错(继续用已有数据): {e}")

    # ===== 第 2 层：精筛（多个策略）=====
    # 构建 code → 粗筛基础指标的映射（layer2 入库时关联补上，避免前端显示空值）
    l1_map = {r["stock_code"]: r for r in result_l1["results"]}
    final_codes = set(codes_l1)
    for strat in strategies:
        if strat not in STRATEGIES:
            print(f"  ⚠️ 未知策略 {strat}，跳过")
            continue
        strat_name = STRATEGIES[strat][0]
        print(f"\n  第 2 层 精筛·{strat_name}({strat}) …")
        try:
            result = run_screener(strat, codes_l1, top_n=top_n)
        except Exception as e:
            print(f"  ⚠️ 策略 {strat} 执行失败: {e}")
            continue

        matched = [r for r in result["results"] if r.get("match")]
        layer2 = {
            "layer": 2, "name": f"精筛·{strat_name}",
            "preset": preset, "strategy": strat,
            "total": result["scanned"], "matched": result["matched"],
        }
        layers.append(layer2)
        print(f"    {layer2['total']} → {layer2['matched']} 只命中")

        # 入库 layer 2（只存命中的，关联 layer1 基础指标）
        rows_l2 = []
        for r in result["results"]:
            l1 = l1_map.get(r["stock_code"], {})
            rows_l2.append({
                "run_id": run_id, "run_date": today, "layer": 2,
                "preset": preset, "strategy": strat,
                "stock_code": r["stock_code"],
                "stock_name": r.get("stock_name") or l1.get("stock_name"),
                "exchange": l1.get("exchange"),
                "total_mv": l1.get("total_mv"), "pe": l1.get("pe"),
                "pb": l1.get("pb"), "turnover": l1.get("turnover"),
                "pct_change": l1.get("pct_change"), "industry": l1.get("industry"),
                "match": 1 if r.get("match") else 0,
                "score": r.get("score"), "reason": r.get("reason"),
                "vol_ratio": r.get("vol_ratio"),
                "macd_signal": r.get("macd_signal"),
                "rsi_value": r.get("rsi_value"),
            })
        if rows_l2:
            n2 = upsert_rows(rows_l2, "screen_result",
                             conflict_cols=["run_id", "layer", "strategy", "stock_code"])

        # 更新最终候选集（取所有策略命中的交集）
        matched_codes = {r["stock_code"] for r in matched}
        final_codes &= matched_codes

    finish_job_run(run_db_id, "ok", rows=sum(l["matched"] for l in layers))

    print(f"\n{'='*60}")
    print(f"✅ 漏斗筛选完成 | run_id: {run_id}")
    for l in layers:
        suffix = f" [{l['strategy']}]" if l.get("strategy") else ""
        print(f"  第{l['layer']}层 {l['name']}{suffix}: {l['total']} → {l['matched']}")
    print(f"  所有策略交集: {len(final_codes)} 只")
    print(f"{'='*60}\n")

    return {
        "run_id": run_id, "preset": preset, "run_date": today,
        "layers": layers,
        "final_codes": sorted(final_codes),
        "final_count": len(final_codes),
    }
