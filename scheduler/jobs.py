"""
定时任务函数 — 拉日线 / 拉分钟线，复用 fetcher + db
"""
import time
import logging

from data.fetchers.akshare_fetcher import fetch_daily, fetch_minute
from data.db import upsert_rows, start_job_run, finish_job_run
from config import STOCK_CODES

from .trading_cal import is_trading_day

logger = logging.getLogger("stock_data_job")


def _run(job_name, fetch_fn, table, conflict_cols):
    """通用任务执行：交易日判断 + 遍历股票池拉取入库 + 记录 job_runs"""
    if not is_trading_day():
        logger.info("%s: 非交易日，跳过", job_name)
        return

    run_id = start_job_run(job_name)
    total = 0
    try:
        n_codes = len(STOCK_CODES)
        for i, code in enumerate(STOCK_CODES, 1):
            logger.info("[%s] %d/%d %s", job_name, i, n_codes, code)
            rows = fetch_fn(code)
            total += upsert_rows(rows, table, conflict_cols)
            time.sleep(0.3)  # akshare 频率限制
        finish_job_run(run_id, "ok", rows=total)
        logger.info("%s 完成，共 %d 条", job_name, total)
    except Exception as e:
        finish_job_run(run_id, "failed", error=str(e))
        logger.exception("%s 失败", job_name)
        raise


def job_fetch_daily():
    """拉取全股票池日线（增量：从 DB 最大日期到今天收盘）

    流程:
      1. 从 stock_pool 最新期次取全部股票代码
      2. 用 batch_fetcher 增量拉取（已有最新交易日的跳过，其余只拉缺失的部分）
      3. 多进程并发（默认 3 进程，BaoStock 安全上限）
    """
    if not is_trading_day():
        logger.info("fetch_daily: 非交易日，跳过")
        return

    # BaoStock 健康检查：login 失败说明 IP 被封，跳过本次避免反复撞击
    import baostock as _bs
    _bs.login()
    _lg = _bs.login()  # 双重确认
    if _lg.error_code != "0":
        logger.warning("fetch_daily: BaoStock 不可用(%s %s)，跳过本次",
                       _lg.error_code, _lg.error_msg)
        _bs.logout()
        return
    _bs.logout()

    run_id = start_job_run("job_fetch_daily")
    try:
        from data.batch_fetcher import fetch_batch
        from data.db import get_engine
        from sqlalchemy import text as _text

        # 从 stock_pool 最新期次取全部股票代码
        engine = get_engine()
        with engine.connect() as conn:
            rows = conn.execute(_text("""
                SELECT DISTINCT stock_code FROM stock_pool
                WHERE trade_date = (SELECT MAX(trade_date) FROM stock_pool)
                ORDER BY stock_code
            """)).fetchall()
        codes = [r[0] for r in rows]
        logger.info("fetch_daily: 股池 %d 只，开始增量拉取", len(codes))

        # 增量拉取（3 进程，BaoStock 安全并发上限）
        total_rows, n_errors = fetch_batch(codes, days=365, workers=3)
        finish_job_run(run_id, "ok" if n_errors == 0 else "partial",
                       rows=total_rows,
                       error=f"{n_errors} 个错误" if n_errors else None)
        logger.info("fetch_daily 完成: %d 条, %d 错误", total_rows, n_errors)
    except Exception as e:
        finish_job_run(run_id, "failed", error=str(e))
        logger.exception("fetch_daily 失败")
        raise


def job_fetch_minute():
    """拉取全股票池当天分钟线（收盘后全量）"""
    _run("job_fetch_minute", fetch_minute, "minute_prices",
         ["stock_code", "trade_time", "period"])


def job_pool():
    """股池月度筛选入库（不判交易日：月末/月初均可跑）"""
    run_id = start_job_run("pool")
    try:
        from data.pool_builder import run_pool
        from config import POOL_NAME
        n = run_pool(pool_name=POOL_NAME)
        finish_job_run(run_id, "ok", rows=n)
        logger.info("pool 完成，共 %d 条", n)
    except Exception as e:
        finish_job_run(run_id, "failed", error=str(e))
        logger.exception("pool 失败")
        raise


def job_signal(force: bool = False):
    """盘后信号扫描：批量评分入库 stock_signal

    参数:
      force: True 时跳过交易日判断（用于 --once 手动调试）
    """
    if not force and not is_trading_day():
        logger.info("signal: 非交易日，跳过")
        return

    run_id = start_job_run("signal")
    try:
        from orchestration.signal_runner import run_daily_signal
        result = run_daily_signal(verbose=False)
        finish_job_run(run_id, "ok", rows=result["scored"])
        logger.info("signal 完成: 共 %d, 评分 %d, 跳过 %d",
                    result["total"], result["scored"], result["skipped"])
    except Exception as e:
        finish_job_run(run_id, "failed", error=str(e))
        logger.exception("signal 失败")
        raise


def job_funnel(force: bool = False):
    """每周漏斗筛选：粗筛 → 拉日线 → 精筛 → 入库 screen_result

    参数:
      force: True 时跳过交易日判断（手动调试用）
    """
    if not force and not is_trading_day():
        logger.info("funnel: 非交易日，跳过")
        return

    run_id = start_job_run("funnel")
    try:
        from orchestration.funnel_runner import run_funnel
        from config import FUNNEL_PRESET, FUNNEL_STRATEGIES
        strategies = FUNNEL_STRATEGIES.split(",")
        result = run_funnel(preset=FUNNEL_PRESET, strategies=strategies)
        finish_job_run(run_id, "ok", rows=result["final_count"])
        logger.info("funnel 完成: run_id=%s, 最终 %d 只",
                    result["run_id"], result["final_count"])
    except Exception as e:
        finish_job_run(run_id, "failed", error=str(e))
        logger.exception("funnel 失败")
        raise


def job_recommend(force: bool = False):
    """每日投资推荐：粗筛 → 4维评分 → 入库 recommend_result"""
    if not force and not is_trading_day():
        logger.info("recommend: 非交易日，跳过")
        return

    run_id = start_job_run("recommend")
    try:
        from orchestration.recommend_runner import run_recommend
        from config import RECOMMEND_PRESET
        result = run_recommend(preset=RECOMMEND_PRESET)
        finish_job_run(run_id, "ok", rows=result["count"])
        logger.info("recommend 完成: run_id=%s, 强烈推荐 %d, 值得关注 %d",
                    result["run_id"], result["strong"], result["watch"])
    except Exception as e:
        finish_job_run(run_id, "failed", error=str(e))
        logger.exception("recommend 失败")
        raise
