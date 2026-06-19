"""
入口脚本

用法:
  python main.py init                          # 初始化数据库
  python main.py fetch_daily                   # 拉取日线（股票池）
  python main.py fetch_daily 600519 000858     # 拉取指定股票日线
  python main.py fetch_minute                  # 拉取当天分钟线（股票池）
  python main.py fetch_minute 600519           # 拉取指定股票分钟线
  python main.py analyze                       # 分析所有股票
  python main.py analyze 600519                # 分析指定股票
  python main.py run                           # 日常一键: 拉日线+分钟线+分析
  python main.py signal                        # 扫描股池信号并评分入库
  python main.py backtest                      # 回测: 历史扫描+收益回填+报告
  python main.py backfill                      # 回填信号收益率
  python main.py backtest_report               # 生成回测报告
"""
import sys
import time

from config import STOCK_CODES
from db import init_db, upsert_rows
from fetcher import fetch_daily, fetch_minute, fetch_stock_list
from analyze import print_report


def do_init():
    """建库建表"""
    init_db()


def do_fetch_daily(codes: list[str] = None):
    """拉取日线数据"""
    codes = codes or STOCK_CODES
    print(f"\n📥 开始拉取日线数据，共 {len(codes)} 只股票\n")
    total = 0
    for i, code in enumerate(codes, 1):
        print(f"  [{i}/{len(codes)}] {code} ...", end=" ")
        try:
            rows = fetch_daily(code)
            n = upsert_rows(rows, "daily_prices", conflict_cols=["stock_code", "trade_date"])
            total += n
            print(f"✅ {n} 条")
            time.sleep(0.3)  # 避免 akshare 频率限制
        except Exception as e:
            print(f"❌ {e}")
    print(f"\n✅ 日线拉取完成，共 {total} 条记录\n")


def do_fetch_minute(codes: list[str] = None):
    """拉取当天分钟线数据"""
    codes = codes or STOCK_CODES
    print(f"\n📥 开始拉取分钟线数据，共 {len(codes)} 只股票\n")
    total = 0
    for i, code in enumerate(codes, 1):
        print(f"  [{i}/{len(codes)}] {code} ...", end=" ")
        try:
            rows = fetch_minute(code)
            n = upsert_rows(rows, "minute_prices", conflict_cols=["stock_code", "trade_time", "period"])
            total += n
            print(f"✅ {n} 条")
            time.sleep(0.3)
        except Exception as e:
            print(f"❌ {e}")
    print(f"\n✅ 分钟线拉取完成，共 {total} 条记录\n")


def do_analyze(codes: list[str] = None):
    """分析报告"""
    codes = codes or STOCK_CODES
    for code in codes:
        print_report(code)


def do_run():
    """日常一键: 初始化 + 拉日线 + 拉分钟线 + 分析"""
    do_init()
    do_fetch_daily()
    do_fetch_minute()
    do_analyze()


def do_pool():
    """股池筛选并入库（以今天为期次）"""
    from a_stock_filter import run_pool
    run_pool()


def do_signal():
    """扫描股池信号并评分入库"""
    from signal_runner import run_daily_signal
    run_daily_signal()


def do_backtest():
    """回测：历史扫描 + 收益回填 + 报告"""
    from signal_backtest import (
        backtest_signals, backfill_returns, analyze_performance, generate_report_md,
    )
    import os
    # 默认回测最近 1 年（公共数据区间）
    from datetime import date, timedelta
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365)
    backtest_signals(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), step=5)
    backfill_returns()
    result = analyze_performance()
    out = os.path.join("spec", "volume-analysis",
                       f"{date.today()}-signal-backtest-report.md")
    generate_report_md(result, out)
    print(f"\n📄 报告已生成: {out}")


def do_backfill():
    """仅回填收益率（已跑过回测）"""
    from signal_backtest import backfill_returns
    backfill_returns()


def do_backtest_report():
    """仅生成报告（基于已有数据）"""
    from signal_backtest import analyze_performance, generate_report_md
    from datetime import date
    import os
    result = analyze_performance()
    out = os.path.join("spec", "volume-analysis",
                       f"{date.today()}-signal-backtest-report.md")
    generate_report_md(result, out)
    print(f"\n📄 报告已生成: {out}")


COMMANDS = {
    "init":             ("初始化数据库",            do_init),
    "fetch_daily":      ("拉取日线数据",            do_fetch_daily),
    "fetch_minute":     ("拉取分钟线数据",          do_fetch_minute),
    "analyze":          ("输出分析报告",            do_analyze),
    "run":              ("日常一键: 拉取 + 分析",    do_run),
    "pool":             ("股池筛选并入库",          do_pool),
    "signal":           ("扫描股池信号并评分入库",   do_signal),
    "backtest":         ("回测: 历史扫描+收益回填+报告", do_backtest),
    "backfill":         ("回填信号收益率",          do_backfill),
    "backtest_report":  ("生成回测报告",            do_backtest_report),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        print("可用命令:")
        for cmd, (desc, _) in COMMANDS.items():
            print(f"  {cmd:<16} {desc}")
        return

    cmd = sys.argv[1]
    extra_args = sys.argv[2:]

    if cmd not in COMMANDS:
        print(f"❌ 未知命令: {cmd}")
        print("可用命令:", ", ".join(COMMANDS.keys()))
        sys.exit(1)

    _, func = COMMANDS[cmd]
    if extra_args:
        func(extra_args)
    else:
        func()


if __name__ == "__main__":
    main()
