"""
批量拉取全股池日线数据（标准功能）

特性:
  1. 只拉最新期次的股票（去重，避免重复代码）
  2. 直接用 BaoStock（跳过本机网络阻断的东方财富）
  3. 增量跳过：已有日线数据的股票自动跳过
  4. 多进程并发：--workers N 启用 N 个进程并发拉取（约 3-4x 加速）
     - BaoStock 不是线程安全的，必须用多进程
     - 每个进程独立 login/logout，带 3 次重试
     - 子进程直接入库（避免跨进程传大数据）
  5. 断点续跑：失败后重跑会自动跳过已成功的

用法:
  # 串行（小批量，100% 成功率，~1.3s/只）
  python -m data.batch_fetcher --from-screen value

  # 3 进程并发（推荐，速度+稳定性平衡，~0.5s/只）
  python -m data.batch_fetcher --workers 3

  # 4 进程并发（最快，但 BaoStock 高并发可能限流导致 ~15% 失败）
  python -m data.batch_fetcher --workers 4

  # 指定粗筛预设 + 并发
  python -m data.batch_fetcher --from-screen growth --top 200 --workers 3

  # 指定代码
  python -m data.batch_fetcher --code 600519,000858

  # 失败补漏：失败的股票再跑一遍串行（增量跳过已成功的）
  python -m data.batch_fetcher --from-screen value

耗时参考（3533 只）:
  串行:   ~78 分钟
  3 进程: ~30 分钟
  4 进程: ~24 分钟
"""
import sys
import time
from datetime import datetime, timedelta

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


def _fetch_one_process(args):
    """进程级独立拉取单只股票并入库（多进程 worker 函数）。

    每个进程独立 login/logout，带重试，成功后直接 upsert 入库。
    返回 (code, rows_count, error)。
    """
    code, days = args
    import baostock as _bs
    from data.fetchers.baostock_fetcher import _to_bs_code, _DAILY_FIELDS, _parse_daily_row
    from data.db import upsert_rows as _upsert
    from datetime import datetime, timedelta

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    for attempt in range(3):
        _bs.login()
        try:
            rs = _bs.query_history_k_data_plus(
                _to_bs_code(code), _DAILY_FIELDS,
                start_date=start, end_date=end,
                frequency="d", adjustflag="2",
            )
            if rs is None or getattr(rs, "error_code", "0") != "0":
                err = getattr(rs, "error_msg", "返回空") if rs else "返回 None"
                _bs.logout()
                if attempt < 2:
                    time.sleep(1)
                    continue
                return code, 0, err
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            _bs.logout()
            # 子进程直接入库
            parsed = [_parse_daily_row(r, code) for r in rows]
            if parsed:
                _upsert(parsed, "daily_prices",
                        conflict_cols=["stock_code", "trade_date"])
            return code, len(parsed), None
        except Exception as e:
            try:
                _bs.logout()
            except Exception:
                pass
            if attempt < 2:
                time.sleep(1)
                continue
            return code, 0, str(e)[:80]
    return code, 0, "3次重试均失败"


def fetch_batch(codes: list, days: int = 365, workers: int = 0):
    """批量拉取日线。

    参数:
      days:    回溯天数
      workers: 并发进程数（0=串行连接复用模式，>0=多进程并发）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    start_full = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 增量判断
    existing = get_existing_latest_dates(codes)
    todo = []
    skipped = 0
    for code in codes:
        last = existing.get(code)
        if last:
            skipped += 1
        else:
            todo.append(code)
    print(f"  总计 {len(codes)} 只 | 跳过(已有) {skipped} 只 | 待拉取 {len(todo)} 只\n")

    if not todo:
        print("  ✅ 全部股票已有数据，无需拉取\n")
        return 0, 0

    if workers > 0:
        return _fetch_batch_parallel(todo, days, workers)
    else:
        return _fetch_batch_serial(todo, start_full, today)


def _fetch_batch_serial(todo, start_full, today):
    """串行模式：BaoStock login 一次，遍历所有代码（适合小批量）"""
    run_id = start_job_run("job_batch_fetch_daily")
    total_rows = 0
    errors = []

    print("  BaoStock 登录中…")
    lg = bs.login()
    if getattr(lg, "error_code", "0") != "0":
        msg = f"BaoStock login 失败: {getattr(lg, 'error_msg', 'unknown')}"
        finish_job_run(run_id, "failed", rows=0, error=msg)
        raise RuntimeError(msg)
    print("  登录成功，开始拉取（串行）\n")

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
                if i % 50 == 0 or i == len(todo):
                    print(f"{prefix} ✅ 累计 {total_rows} 条 (进度 {i/len(todo)*100:.1f}%)")
                time.sleep(0.05)
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


def _fetch_batch_parallel(todo, days, workers):
    """多进程并发模式：每个进程独立 login（适合大批量，~4x 加速）"""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from data.fetchers.baostock_fetcher import _parse_daily_row

    run_id = start_job_run("job_batch_fetch_daily")
    total_rows = 0
    errors = []
    done = 0

    print(f"  多进程并发拉取（{workers} 进程）开始…\n")

    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_one_process, (code, days)): code
                       for code in todo}
            for future in as_completed(futures):
                code = futures[future]
                done += 1
                try:
                    fc, count, err = future.result()
                    if err:
                        errors.append({"code": fc, "error": err})
                    else:
                        total_rows += count
                    if done % 50 == 0 or done == len(todo):
                        pct = done / len(todo) * 100
                        print(f"  [{done}/{len(todo)}] 进度 {pct:.1f}% | "
                              f"累计 {total_rows} 条 | 错误 {len(errors)}")
                except Exception as e:
                    errors.append({"code": code, "error": str(e)[:100]})
    except Exception as e:
        print(f"  ⚠️ 并发执行异常: {e}")

    finish_job_run(run_id, "ok" if not errors else "partial",
                   rows=total_rows, error=str(errors[:5]) if errors else None)
    print(f"\n✅ 并发拉取完成: {len(todo)-len(errors)}/{len(todo)} 成功, {len(errors)} 错误\n")
    return total_rows, len(errors)


if __name__ == "__main__":
    from datetime import timedelta

    # 解析命令行参数
    limit = None
    codes = None
    from_screen = None
    top_n = None
    workers = 0
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
        elif arg == "--workers" and i + 1 < len(args):
            workers = int(args[i + 1])

    # 确定拉取范围
    if from_screen:
        # 从粗筛结果取代码
        from core.screeners.pool_screener import list_codes, PRESETS
        if from_screen not in PRESETS:
            print(f"未知粗筛预设: {from_screen}，可选: {list(PRESETS.keys())}")
            sys.exit(1)
        target = list_codes(preset=from_screen, top_n=top_n)
        mode = f"{workers}进程并发" if workers > 0 else "串行"
        print(f"\n📥 批量拉取日线（粗筛 {from_screen}，{len(target)} 只，{mode}）\n")
    else:
        target = get_latest_pool_codes(limit=limit, codes=codes)
        mode = f"{workers}进程并发" if workers > 0 else "串行"
        print(f"\n📥 批量拉取日线数据（最新期次，{len(target)} 只，{mode}）\n")

    fetch_batch(target, days=365, workers=workers)
