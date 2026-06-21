"""
python -m scheduler 入口

用法:
  python -m scheduler                    # 常驻调度
  python -m scheduler --once daily       # 立即跑一次日线任务（调试）
  python -m scheduler --once minute      # 立即跑一次分钟线任务（调试）
  python -m scheduler --once pool        # 立即跑一次股池筛选（调试）
  python -m scheduler --once signal      # 立即跑一次信号扫描（调试）
  python -m scheduler --once funnel      # 立即跑一次漏斗筛选（调试）
"""
import argparse
import logging

from config import JOB_LOG_FILE

from .jobs import job_fetch_daily, job_fetch_minute, job_pool, job_signal, job_funnel
from .scheduler import build_scheduler


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(JOB_LOG_FILE, encoding="utf-8")],
    )


def main():
    parser = argparse.ArgumentParser(prog="scheduler",
                                     description="股票数据定时拉取")
    parser.add_argument("--once", choices=["daily", "minute", "pool", "signal", "funnel"],
                        help="立即执行一次指定任务，不进调度循环")
    args = parser.parse_args()

    _setup_logging()

    if args.once == "daily":
        job_fetch_daily()
    elif args.once == "minute":
        job_fetch_minute()
    elif args.once == "pool":
        job_pool()
    elif args.once == "signal":
        job_signal(force=True)
    elif args.once == "funnel":
        job_funnel(force=True)
    else:
        sched = build_scheduler()
        print("scheduler 调度器已启动，按 Ctrl+C 退出")
        sched.start()


if __name__ == "__main__":
    main()
