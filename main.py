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
  python main.py screen trend                  # 量化策略筛选(趋势/突破/回调/动量)
  python main.py screen breakout 30            # 指定策略+返回数量
  python main.py fetch_chip                    # 计算全部股票筹码分布(近90天)
  python main.py fetch_chip 600519             # 指定股票筹码分布
  python main.py fetch_chip 600519 30          # 指定股票+最近30天
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
    """拉取日线数据（增量：有历史数据的从最后交易日+1开始，无历史的全量回溯）"""
    from db import get_last_trade_dates
    codes = codes or STOCK_CODES
    print(f"\n📥 开始拉取日线数据（增量），共 {len(codes)} 只股票\n")

    # 批量查每只股票最后交易日
    last_dates = get_last_trade_dates(codes)
    full_count = len(codes) - len(last_dates)  # 无历史数据，需全量
    incr_count = len(last_dates)               # 有历史，增量
    print(f"  增量拉取: {incr_count} 只 | 全量拉取(首次): {full_count} 只\n")

    total = 0
    for i, code in enumerate(codes, 1):
        last = last_dates.get(code)
        if last:
            # 增量：从最后交易日次日开始（YYYYMMDD 格式，去掉横线）
            start = last.replace("-", "")
            mode = f"增量({last}起)"
        else:
            start = None  # 全量回溯 HISTORY_DAYS
            mode = "全量"

        print(f"  [{i}/{len(codes)}] {code} {mode} ...", end=" ")
        try:
            rows = fetch_daily(code, start_date=start)
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


def do_fetch_chip(codes: list[str] = None, days: int = 90):
    """计算并入库筹码分布数据（本地复现 CYQ 算法，不依赖外部接口）

    用法:
      python main.py fetch_chip              # 股池全部股票，最近 90 天
      python main.py fetch_chip 600519       # 指定股票
      python main.py fetch_chip 600519 30    # 指定股票 + 最近 30 天
    """
    import time as _t
    from chip_fetcher import upsert_chip
    from db import get_engine
    from sqlalchemy import text

    # 解析参数：codes（位置参数列表）+ days（最后一个数字）
    if isinstance(codes, list):
        # 末尾是数字则当作 days
        if codes and codes[-1].isdigit():
            days = int(codes.pop())
        codes = codes or None

    if codes:
        target_codes = codes
    else:
        # 默认取有日线数据的全部股票
        e = get_engine()
        with e.connect() as conn:
            rows = conn.execute(text(
                "SELECT DISTINCT stock_code FROM daily_prices"
            )).fetchall()
        target_codes = [r[0] for r in rows]

    print(f"\n📥 开始计算筹码分布（本地 CYQ 算法），共 {len(target_codes)} 只股票，最近 {days} 天\n")
    total = 0
    for i, code in enumerate(target_codes, 1):
        print(f"  [{i}/{len(target_codes)}] {code} ...", end=" ")
        try:
            n = upsert_chip(code, days=days)
            total += n
            print(f"✅ {n} 条")
        except Exception as e:
            print(f"❌ {e}")
        _t.sleep(0.05)  # 本地计算，间隔极短
    print(f"\n✅ 筹码分布计算完成，共 {total} 条记录\n")


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


def do_screen(args=None):
    """量化策略筛选（趋势/突破/回调/动量）

    用法:
      python main.py screen trend                   # 全部有日线股票
      python main.py screen trend 30                # 前 30
      python main.py screen trend --from-pool value # 仅对粗筛"价值蓝筹"的结果精筛
    """
    args = args or []
    from strategy_screener import run_screener, STRATEGIES
    from db import get_engine
    from sqlalchemy import text

    # 解析参数：python main.py screen [strategy] [top_n] [--from-pool PRESET]
    strategy = args[0] if len(args) > 0 else "trend"
    top_n = 50
    from_pool = None
    for a in args[1:]:
        if a == "--from-pool":
            idx = args.index(a) + 1
            from_pool = args[idx] if idx < len(args) else None
        elif a.startswith("--"):
            continue
        elif a.isdigit():
            top_n = int(a)

    if strategy not in STRATEGIES:
        print(f"未知策略: {strategy}")
        print(f"可选: {', '.join(f'{k}({v[0]})' for k, v in STRATEGIES.items())}")
        return

    # 确定精筛范围
    if from_pool:
        from pool_screener import list_codes
        codes = list_codes(preset=from_pool)
        print(f"📐 粗筛预设 {from_pool}: {len(codes)} 只候选股")
    else:
        e = get_engine()
        with e.connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT stock_code FROM daily_prices")).fetchall()
        codes = [r[0] for r in rows]

    result = run_screener(strategy, codes, top_n=top_n)
    print(f"\n{'='*70}")
    print(f"🎯 策略: {result['strategy_name']} | 扫描 {result['scanned']} 只 | 命中 {result['matched']} 只")
    print(f"{'='*70}")
    print(f"\nTop {len(result['results'])}:")
    for i, r in enumerate(result["results"], 1):
        match_mark = "✅" if r["match"] else "  "
        extra = f" | 20日涨{r.get('return_20d', 0):+.1f}%" if strategy == "momentum" else ""
        print(f"  {i:>2}. {match_mark} {r['stock_code']} {r.get('stock_name', ''):<8} "
              f"得分{r['score']:>5.1f}{extra}")
        print(f"      └ {r['reason']}")
    print(f"{'='*70}\n")


def do_screen_pool(args=None):
    """股池基础粗筛（基于市值/PE/PB/换手率等快照指标，零网络开销）

    用法:
      python main.py screen_pool                         # 列出可用预设
      python main.py screen_pool value                   # 价值蓝筹
      python main.py screen_pool growth --top 50         # 成长活跃 前50
      python main.py screen_pool --custom "total_mv>100,pe>0,turnover>1"
    """
    args = args or []
    from pool_screener import screen_pool, print_screen_result, PRESETS

    # 无参数：列出预设
    if not args:
        print("\n📋 可用粗筛预设:")
        print(f"{'='*60}")
        for key, p in PRESETS.items():
            print(f"\n  {key:<14} {p.label}")
            print(f"  {' '*14} {p.desc}")
            print(f"  {' '*14} 适用: {', '.join(p.tags)}")
        print(f"\n{'='*60}")
        print("\n用法: python main.py screen_pool <预设名> [--top N]")
        print("      python main.py screen_pool --custom '条件1,条件2'\n")
        return

    # 解析参数
    preset = None
    custom = None
    top_n = None
    skip_next = False
    for i, a in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if a == "--custom":
            custom = args[i + 1] if i + 1 < len(args) else None
            skip_next = True
        elif a == "--top":
            top_n = int(args[i + 1]) if i + 1 < len(args) else None
            skip_next = True
        elif not a.startswith("--"):
            preset = a

    result = screen_pool(preset=preset, custom=custom, top_n=top_n)
    print_screen_result(result)


def do_funnel(args=None):
    """漏斗筛选：粗筛 → 拉日线 → 精筛 → 入库

    用法:
      python main.py funnel                    # 默认 value + trend/breakout/momentum
      python main.py funnel growth             # 指定预设
      python main.py funnel value trend        # 指定预设+策略
      python main.py funnel value trend breakout  # 多策略
    """
    args = args or []
    from funnel_runner import run_funnel
    from pool_screener import PRESETS
    from strategy_screener import STRATEGIES

    preset = args[0] if args and not args[0].startswith("-") else "value"
    strategies = [a for a in args[1:] if not a.startswith("-")] or None

    if preset not in PRESETS:
        print(f"未知预设: {preset}，可选: {list(PRESETS.keys())}")
        return

    run_funnel(preset=preset, strategies=strategies)


COMMANDS = {
    "init":             ("初始化数据库",            do_init),
    "fetch_daily":      ("拉取日线数据",            do_fetch_daily),
    "fetch_minute":     ("拉取分钟线数据",          do_fetch_minute),
    "analyze":          ("输出分析报告",            do_analyze),
    "run":              ("日常一键: 拉取 + 分析",    do_run),
    "pool":             ("股池筛选并入库",          do_pool),
    "screen_pool":      ("股池基础粗筛(市值/PE/换手等)", do_screen_pool),
    "funnel":           ("漏斗筛选(粗筛→精筛→入库)", do_funnel),
    "fetch_chip":       ("计算并入库筹码分布(本地CYQ算法)", do_fetch_chip),
    "signal":           ("扫描股池信号并评分入库",   do_signal),
    "backtest":         ("回测: 历史扫描+收益回填+报告", do_backtest),
    "backfill":         ("回填信号收益率",          do_backfill),
    "backtest_report":  ("生成回测报告",            do_backtest_report),
    "screen":           ("量化策略筛选(趋势/突破/回调/动量)", do_screen),
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
