"""
投资推荐编排器（recommend_runner）

对粗筛候选股计算 4 维推荐分并入库 recommend_result 表。

用法:
  python main.py recommend              # 默认 value 预设
  python main.py recommend growth       # 指定预设
"""
from __future__ import annotations

from datetime import date

from data.db import upsert_rows, start_job_run, finish_job_run, \
    query_daily, query_chip_latest


def run_recommend(preset: str = "value", top_n: int = 100,
                  skip_fetch: bool = False) -> dict:
    """对粗筛结果计算推荐分并入库。

    参数:
      preset:      粗筛预设 (value/growth/breakout/oversold/dividend/all_active)
      top_n:       最多评分多少只（按市值排序取前 N）
      skip_fetch:  跳过日线/筹码拉取（假设已有数据）
    """
    from core.screeners.pool_screener import screen_pool, PRESETS
    from core.scoring.recommender import score_stock_recommendation

    if preset not in PRESETS:
        raise ValueError(f"未知预设: {preset}，可选: {list(PRESETS.keys())}")

    today = date.today().isoformat()
    run_id = f"{today}-{preset}"

    print(f"\n{'='*60}")
    print(f"💡 投资推荐计算 | 预设: {PRESETS[preset].label}({preset}) | run_id: {run_id}")
    print(f"{'='*60}\n")

    run_db_id = start_job_run("job_recommend")

    # 1. 粗筛
    result = screen_pool(preset=preset, top_n=top_n)
    candidates = result["results"]
    print(f"  粗筛: {result['matched']} 只 → 取前 {len(candidates)} 只评分\n")

    if not candidates:
        finish_job_run(run_db_id, "ok", rows=0)
        return {"run_id": run_id, "count": 0}

    # 2. 增量拉数据
    if not skip_fetch:
        from data.batch_fetcher import fetch_batch
        codes = [c["stock_code"] for c in candidates]
        try:
            print("  📥 增量拉取日线…")
            fetch_batch(codes, days=365)
        except Exception as e:
            print(f"  ⚠️ 日线拉取出错(用已有数据): {e}")

    # 3. 逐只评分
    results = []
    total = len(candidates)
    for i, c in enumerate(candidates, 1):
        code = c["stock_code"]
        try:
            daily_df = query_daily(code, limit=250)
            chip = query_chip_latest(code)
            rec = score_stock_recommendation(
                code, c.get("stock_name"), daily_df, c, chip)
            rec["run_id"] = run_id
            rec["run_date"] = today
            results.append(rec)
            if i % 20 == 0 or i == total:
                strong = sum(1 for r in results if r["label"] == "强烈推荐")
                print(f"  [{i}/{total}] 已评分 | 强烈推荐 {strong} 只")
        except Exception as e:
            print(f"  [{i}/{total}] {code} 评分失败: {e}")

    # 4. 分批入库（避免大批量 upsert 导致 MySQL 连接超时）
    if results:
        batch_size = 200
        total_n = 0
        for i in range(0, len(results), batch_size):
            chunk = results[i:i + batch_size]
            n = upsert_rows(chunk, "recommend_result",
                            conflict_cols=["run_id", "stock_code"])
            total_n += n
        print(f"\n  入库: {total_n} 条（{len(results)} 只，分 {(len(results)-1)//batch_size+1} 批）")

    # 5. 统计
    strong = sum(1 for r in results if r["label"] == "强烈推荐")
    watch = sum(1 for r in results if r["label"] == "值得关注")
    finish_job_run(run_db_id, "ok", rows=len(results))

    print(f"\n{'='*60}")
    print(f"✅ 推荐完成 | run_id: {run_id}")
    print(f"  强烈推荐: {strong} 只 | 值得关注: {watch} 只 | 共 {len(results)} 只")
    print(f"{'='*60}\n")

    return {
        "run_id": run_id, "preset": preset, "count": len(results),
        "strong": strong, "watch": watch,
    }
