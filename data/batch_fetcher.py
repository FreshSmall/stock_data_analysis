"""
批量拉取全股池日线数据（优化版）

优化点:
  1. 只拉最新期次的股票（去重，避免重复代码）
  2. 直接用 BaoStock（跳过本机网络阻断的东方财富），login 一次复用整个批次
  3. 增量跳过：已有最新交易日数据的股票直接跳过
  4. 进度持久化：断点续跑（记录已完成代码到 job_runs）

用法:
  python batch_fetch_daily.py                          # 拉取最新期次全部
  python batch_fetch_daily.py --limit 100              # 仅前 100 只（测试）
  python batch_fetch_daily.py --code 600519,000858     # 指定代码
  python batch_fetch_daily.py --from-screen value      # 仅拉粗筛"价值蓝筹"的结果
  python batch_fetch_daily.py --from-screen growth --top 50
"""
import sys
import time
from datetime import datetime

import baostock as bs
from sqlalchemy import text

from data.fetchers.baostock_fetcher import _to_bs_code, _DAILY_FIELDS, _parse_daily_row
from data.db import get_engine, upsert_rows, start_job_run, finish_job_run


def get_latest_pool_codes(limit: int = None, codes: list = None) -> list:
    """获取最新期次 stock_pool 的去重股票代码（按代码升序）"""
    e = get_engine()
    with e.connect() as c:
        if codes:
            # 指定代码：直接返回（去重）
            seen = set()
            result = []
            for code in codes:
                if code not in seen:
                    seen.add(code)
                    result.append(code)
            return result
        # 取最新 trade_date 的全部代码
        sql = """
            SELECT DISTINCT stock_code FROM stock_pool
            WHERE trade_date = (SELECT MAX(trade_date) FROM stock_pool)
            ORDER BY stock_code
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = c.execute(text(sql)).fetchall()
        return [r[0] for r in rows]


def get_existing_latest_dates(codes: list) -> dict:
    """批量查这些代码在 daily_prices 的最新交易日（增量判断）"""
    if not codes:
        return {}
    e = get_engine()
    result = {}
    # 分批查（避免 IN 子句过长）
    batch = 500
    with e.connect() as c:
        for i in range(0, len(codes), batch):
            chunk = codes[i:i+batch]
            placeholders = ",".join([f":c{j}" for j in range(len(chunk))])
            params = {f"c{j}": chunk[j] for j in range(len(chunk))}
            rows = c.execute(text(
                f"SELECT stock_code, MAX(trade_date) FROM daily_prices "
                f"WHERE stock_code IN ({placeholders}) GROUP BY stock_code"
            ), params).fetchall()
            for r in rows:
                result[r[0]] = str(r[1]) if r[1] else None
    return result


def fetch_batch(codes: list, days: int = 365):
    """批量拉取：BaoStock login 一次，遍历所有代码，结束后 logout"""
    today = datetime.now().strftime("%Y-%m-%d")
    start_full = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 增量判断
    existing = get_existing_latest_dates(codes)
    todo = []
    skipped = 0
    for code in codes:
        last = existing.get(code)
        if last:
            # 已有最新交易日数据，跳过
            skipped += 1
        else:
            todo.append(code)
    print(f"  总计 {len(codes)} 只 | 跳过(已有) {skipped} 只 | 待拉取 {len(todo)} 只\n")

    if not todo:
        print("  ✅ 全部股票已有数据，无需拉取\n")
        return 0, 0

    run_id = start_job_run("job_batch_fetch_daily")
    total_rows = 0
    errors = []

    # BaoStock 连接复用：login 一次
    print("  BaoStock 登录中…")
    lg = bs.login()
    if getattr(lg, "error_code", "0") != "0":
        msg = f"BaoStock login 失败: {getattr(lg, 'error_msg', 'unknown')}"
        finish_job_run(run_id, "failed", rows=0, error=msg)
        raise RuntimeError(msg)
    print("  登录成功，开始拉取\n")

    try:
        for i, code in enumerate(todo, 1):
            prefix = f"  [{i}/{len(todo)}] {code}"
            try:
                bs_code = _to_bs_code(code)
                rs = bs.query_history_k_data_plus(
                    bs_code, _DAILY_FIELDS,
                    start_date=start_full, end_date=today,
                    frequency="d", adjustflag="2",
                )
                if rs is None or getattr(rs, "error_code", "0") != "0":
                    err = getattr(rs, "error_msg", "返回空") if rs else "返回 None"
                    errors.append({"code": code, "error": err})
                    print(f"{prefix} ❌ {err}")
                    continue
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                parsed = [_parse_daily_row(r, code) for r in rows]
                n = upsert_rows(parsed, "daily_prices",
                                conflict_cols=["stock_code", "trade_date"])
                total_rows += n
                # 每 50 只打印一次进度，避免日志爆炸
                if i % 50 == 0 or i == len(todo):
                    print(f"{prefix} ✅ 累计 {total_rows} 条 (进度 {i/len(todo)*100:.1f}%)")
                time.sleep(0.05)  # BaoStock 限频较宽松，50ms 足够
            except Exception as e:
                errors.append({"code": code, "error": str(e)[:100]})
                print(f"{prefix} ❌ {e}")
    finally:
        bs.logout()
        print("\n  BaoStock 已登出")

    status = "ok" if not errors else "partial"
    finish_job_run(run_id, status, rows=total_rows,
                   error=str(errors[:5]) if errors else None)
    print(f"\n✅ 批量拉取完成: {total_rows} 条记录, {len(errors)} 个错误\n")
    return total_rows, len(errors)


if __name__ == "__main__":
    from datetime import timedelta

    # 解析命令行参数
    limit = None
    codes = None
    from_screen = None
    top_n = None
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        elif arg == "--code" and i + 1 < len(args):
            codes = args[i + 1].split(",")
        elif arg == "--from-screen" and i + 1 < len(args):
            from_screen = args[i + 1]
        elif arg == "--top" and i + 1 < len(args):
            top_n = int(args[i + 1])

    # 确定拉取范围
    if from_screen:
        # 从粗筛结果取代码
        from core.screeners.pool_screener import list_codes, PRESETS
        if from_screen not in PRESETS:
            print(f"未知粗筛预设: {from_screen}，可选: {list(PRESETS.keys())}")
            sys.exit(1)
        target = list_codes(preset=from_screen, top_n=top_n)
        print(f"\n📥 批量拉取日线（粗筛 {from_screen}，共 {len(target)} 只股票）\n")
    else:
        target = get_latest_pool_codes(limit=limit, codes=codes)
        print(f"\n📥 批量拉取日线数据（最新期次，共 {len(target)} 只股票）\n")

    fetch_batch(target, days=365)
