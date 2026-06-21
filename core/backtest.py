"""
信号系统回测 — 历史扫描 + 收益回填 + 分标签胜率统计

设计文档: spec/volume-analysis/2026-06-17-volume-analysis-system-design.md §11 验收6

功能:
  1. backtest_signals(): 对历史交易日逐日评分，回填 stock_signal_log
  2. backfill_returns(): 对已有信号按 signal_date + 5/20 交易日查后续 close，回填收益率
  3. analyze_performance(): 分标签统计 next_5d/20d_return 均值与正收益占比（胜率）

用法:
  python main.py backtest              # 跑回测 + 回填 + 出报告
  python main.py backfill_returns      # 仅回填收益率（已跑过回测）
  python main.py backtest_report       # 仅生成报告（基于已有数据）
"""
from datetime import date, timedelta
from typing import Optional

import pandas as pd
from sqlalchemy import text, bindparam

from data.db import get_engine
from core.scoring.signal_scorer import score_batch


# ============ 1. 历史扫描 ============

def _get_trading_dates(start_date: str, end_date: str) -> list:
    """从 daily_prices 取交易日列表（去重升序）。"""
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT DISTINCT trade_date FROM daily_prices
        WHERE trade_date BETWEEN :s AND :e
        ORDER BY trade_date
    """), engine, params={"s": start_date, "e": end_date})
    return df["trade_date"].tolist()


def backtest_signals(start_date: str, end_date: str,
                     stock_codes: list = None,
                     step: int = 5, verbose: bool = True) -> dict:
    """对历史区间逐日评分，写入 stock_signal_log。

    性能优化: 一次性预取全区间 daily 数据到内存，按交易日切片复用，
    避免每个采样日重复查 DB（区别于 signal_scorer.score_batch 的逐日预取）。

    参数:
      start_date/end_date: 回测区间
      stock_codes: 指定股票（None=全部有数据的股票）
      step: 每隔 N 个交易日扫描一次（默认 5，即周频，避免数据量过大）
      verbose: 打印进度

    返回: {'days_scanned', 'signals_written', 'skipped'}
    """
    import core.indicators.analyze
    import core.indicators.volume_engine

    trading_days = _get_trading_dates(start_date, end_date)
    if not trading_days:
        return {"days_scanned": 0, "signals_written": 0, "skipped": 0}

    engine = get_engine()

    # 确定回测股票池 + 一次性预取全区间日线
    if stock_codes is None:
        rows = engine.connect().execute(text("""
            SELECT DISTINCT stock_code FROM daily_prices
            WHERE trade_date BETWEEN :s AND :e
        """), {"s": start_date, "e": end_date}).fetchall()
        stock_codes = [r[0] for r in rows]

    # 一次性查全区间 daily（expanding bindparam）
    df_all = pd.read_sql(text("""
        SELECT * FROM daily_prices
        WHERE trade_date BETWEEN :s AND :e
        AND stock_code IN :codes
        ORDER BY stock_code, trade_date
    """).bindparams(bindparam("codes", expanding=True)),
        engine, params={"s": start_date, "e": end_date, "codes": stock_codes})
    # 按股票分组，每只股票的完整日线序列（升序）
    daily_by_code = {code: g.reset_index(drop=True)
                     for code, g in df_all.groupby("stock_code")}

    # 按 step 抽样交易日（周频）
    sampled_days = trading_days[::step]
    if verbose:
        print(f"\n📊 回测区间: {start_date} ~ {end_date}")
        print(f"   交易日 {len(trading_days)} 个，抽样 {len(sampled_days)} 个（每{step}天）")
        print(f"   股票池 {len(stock_codes)} 只\n")

    all_records = []
    # 预取的分钟数据：回测无分钟线，统一 None
    from core.scoring.signal_scorer import score_stock

    for i, dt in enumerate(sampled_days):
        dt_str = str(dt)[:10]
        for code in stock_codes:
            df_code = daily_by_code.get(code)
            if df_code is None or df_code.empty:
                continue
            # 切片到信号日（含），用截止该日的数据进行评分
            mask = df_code["trade_date"].astype(str).str[:10] <= dt_str
            df_slice = df_code[mask].reset_index(drop=True)
            if df_slice.empty:
                continue
            try:
                rec = score_stock(code, signal_date=dt, daily_df=df_slice, minute_df=None)
            except Exception:
                continue
            if rec is None:
                continue
            label, action = _label_action(rec["label"])
            all_records.append({
                "stock_code": code,
                "signal_date": rec["signal_date"],
                "score": rec["score"],
                "label": rec["label"],
                "action": action,
            })
        if verbose and (i + 1) % 10 == 0:
            print(f"   进度: {i+1}/{len(sampled_days)} 天, 累计信号 {len(all_records)}")

    # 写入 stock_signal_log（区间内先删后插，避免重复）
    n_written = 0
    if all_records:
        with engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM stock_signal_log
                WHERE signal_date BETWEEN :s AND :e
            """), {"s": start_date, "e": end_date})
        df_log = pd.DataFrame(all_records)
        df_log.to_sql("stock_signal_log", engine, if_exists="append", index=False)
        n_written = len(all_records)

    if verbose:
        print(f"\n✅ 回测完成: 扫描 {len(sampled_days)} 天, 写入 {n_written} 条信号")
    return {"days_scanned": len(sampled_days),
            "signals_written": n_written, "skipped": 0}


def _label_action(label: str) -> tuple:
    """标签 → 建议动作（与 signal_scorer.map_label 对齐）。"""
    actions = {"强烈关注": "关注", "值得关注": "观察", "中性观察": "无", "暂不参与": "回避"}
    return label, actions.get(label, "无")


# ============ 2. 收益率回填 ============

def backfill_returns(verbose: bool = True) -> int:
    """对 stock_signal_log 已有记录，回填 next_5d_return / next_20d_return。

    方法: 按 stock_code 分组，取 signal_date 当日 close，再找 +5/+20 交易日的 close，
    收益率 = (future_close - signal_close) / signal_close * 100。
    """
    engine = get_engine()
    df_log = pd.read_sql(text("""
        SELECT id, stock_code, signal_date
        FROM stock_signal_log
        WHERE next_5d_return IS NULL OR next_20d_return IS NULL
    """), engine)

    if df_log.empty:
        if verbose:
            print("无待回填记录")
        return 0

    if verbose:
        print(f"\n🔄 回填收益率: {len(df_log)} 条待处理")

    # 批量取所有涉及股票的日线（用 expanding bindparam 支持 IN 子句）
    codes = df_log["stock_code"].unique().tolist()
    df_daily = pd.read_sql(text("""
        SELECT stock_code, trade_date, close
        FROM daily_prices
        WHERE stock_code IN :codes
        ORDER BY stock_code, trade_date
    """).bindparams(bindparam("codes", expanding=True)),
        engine, params={"codes": codes})

    updates = []
    for _, log_row in df_log.iterrows():
        code = log_row["stock_code"]
        sig_date = str(log_row["signal_date"])[:10]
        sub = df_daily[df_daily["stock_code"] == code].sort_values("trade_date").reset_index(drop=True)
        idx = sub.index[sub["trade_date"].astype(str).str[:10] == sig_date].tolist()
        if not idx:
            continue
        i = idx[0]
        sig_close = float(sub.iloc[i]["close"])
        r5 = _calc_future_return(sub, i, 5, sig_close)
        r20 = _calc_future_return(sub, i, 20, sig_close)
        updates.append({"id": int(log_row["id"]),
                        "next_5d_return": r5, "next_20d_return": r20})

    # 批量更新（用 CASE WHEN 一次性更新，避免逐条 UPDATE）
    if updates:
        with engine.begin() as conn:
            for u in updates:
                conn.execute(text("""
                    UPDATE stock_signal_log
                    SET next_5d_return = CAST(:r5 AS DECIMAL(8,4)),
                        next_20d_return = CAST(:r20 AS DECIMAL(8,4))
                    WHERE id = :id
                """), {"id": u["id"],
                       "r5": u["next_5d_return"],
                       "r20": u["next_20d_return"]})
    if verbose:
        print(f"✅ 回填完成: {len(updates)} 条（不足5/20交易日的字段为NULL）")
    return len(updates)


def _calc_future_return(sub: pd.DataFrame, idx: int, n_days: int,
                        sig_close: float) -> Optional[float]:
    """计算 idx 后 n_days 个交易日的收益率。数据不足返回 None。"""
    future_idx = idx + n_days
    if future_idx >= len(sub):
        return None
    future_close = float(sub.iloc[future_idx]["close"])
    if sig_close == 0:
        return None
    return round((future_close - sig_close) / sig_close * 100, 4)


# ============ 3. 胜率统计 + 报告 ============

def analyze_performance(verbose: bool = True) -> dict:
    """分标签统计 next_5d/20d_return 的均值与正收益占比（胜率）。

    返回: {
      'by_label': {label: {'n', 'r5_mean', 'r5_win', 'r20_mean', 'r20_win'}},
      'by_score_bucket': {bucket: {...}},
      'summary': {...}
    }
    """
    engine = get_engine()
    df = pd.read_sql(text("""
        SELECT label, score, next_5d_return, next_20d_return
        FROM stock_signal_log
        WHERE next_5d_return IS NOT NULL OR next_20d_return IS NOT NULL
    """), engine)

    if df.empty:
        if verbose:
            print("⚠ 无回填数据，请先运行 backfill_returns")
        return {"by_label": {}, "by_score_bucket": {}, "summary": {}}

    result = {"by_label": {}, "by_score_bucket": {}, "summary": {}}

    # 按标签统计
    for label in ["强烈关注", "值得关注", "中性观察", "暂不参与"]:
        sub = df[df["label"] == label]
        if sub.empty:
            continue
        result["by_label"][label] = _stats(sub)

    # 按评分分桶（10 分一档）
    for lo in range(0, 100, 10):
        hi = lo + 10
        sub = df[(df["score"] >= lo) & (df["score"] < hi)]
        if sub.empty:
            continue
        result["by_score_bucket"][f"{lo}-{hi}"] = _stats(sub)

    # 汇总
    result["summary"] = {
        "total_signals": len(df),
        "has_5d_return": int(df["next_5d_return"].notna().sum()),
        "has_20d_return": int(df["next_20d_return"].notna().sum()),
        "label_distribution": df["label"].value_counts().to_dict(),
    }

    if verbose:
        _print_report(result)
    return result


def _stats(sub: pd.DataFrame) -> dict:
    """计算一组信号的收益率统计。"""
    r5 = sub["next_5d_return"].dropna()
    r20 = sub["next_20d_return"].dropna()
    return {
        "n": len(sub),
        "r5_mean": round(float(r5.mean()), 2) if len(r5) else None,
        "r5_win": round(float((r5 > 0).mean() * 100), 1) if len(r5) else None,
        "r20_mean": round(float(r20.mean()), 2) if len(r20) else None,
        "r20_win": round(float((r20 > 0).mean() * 100), 1) if len(r20) else None,
    }


def _print_report(result: dict):
    """控制台打印回测报告。"""
    print(f"\n{'='*70}")
    print("📈 信号系统回测报告")
    print(f"{'='*70}")
    s = result["summary"]
    print(f"总信号数: {s['total_signals']} | 有5日收益: {s['has_5d_return']} | 有20日收益: {s['has_20d_return']}")
    print(f"标签分布: {s['label_distribution']}")

    print(f"\n--- 按标签统计 ---")
    print(f"{'标签':<10} {'样本':>6} {'5日均值':>8} {'5日胜率':>8} {'20日均值':>9} {'20日胜率':>9}")
    for label in ["强烈关注", "值得关注", "中性观察", "暂不参与"]:
        st = result["by_label"].get(label)
        if not st:
            continue
        print(f"{label:<10} {st['n']:>6} "
              f"{(str(st['r5_mean'])+'%') if st['r5_mean'] is not None else '-':>8} "
              f"{(str(st['r5_win'])+'%') if st['r5_win'] is not None else '-':>8} "
              f"{(str(st['r20_mean'])+'%') if st['r20_mean'] is not None else '-':>9} "
              f"{(str(st['r20_win'])+'%') if st['r20_win'] is not None else '-':>9}")

    print(f"\n--- 按评分分桶统计（10分一档）---")
    print(f"{'区间':<10} {'样本':>6} {'5日均值':>8} {'5日胜率':>8} {'20日均值':>9} {'20日胜率':>9}")
    for bucket in sorted(result["by_score_bucket"].keys()):
        st = result["by_score_bucket"][bucket]
        print(f"{bucket:<10} {st['n']:>6} "
              f"{(str(st['r5_mean'])+'%') if st['r5_mean'] is not None else '-':>8} "
              f"{(str(st['r5_win'])+'%') if st['r5_win'] is not None else '-':>8} "
              f"{(str(st['r20_mean'])+'%') if st['r20_mean'] is not None else '-':>9} "
              f"{(str(st['r20_win'])+'%') if st['r20_win'] is not None else '-':>9}")

    # 区分度判断
    ex = result["by_label"].get("强烈关注", {})
    poor = result["by_label"].get("暂不参与", {})
    if ex.get("r20_win") and poor.get("r20_win"):
        diff = ex["r20_win"] - poor["r20_win"]
        verdict = "✅ 有区分度" if diff > 5 else "⚠ 区分度不足"
        print(f"\n区分度: 强烈关注 20日胜率({ex['r20_win']}%) - 暂不参与({poor['r20_win']}%) = {diff:+.1f}% {verdict}")
    print(f"{'='*70}\n")


def generate_report_md(result: dict, output_path: str) -> str:
    """生成 Markdown 回测报告并写入文件。"""
    s = result["summary"]
    lines = [
        "# 信号系统回测报告",
        "",
        f"> 生成时间: {date.today()}",
        f"> 总信号数: {s['total_signals']} | 有5日收益: {s['has_5d_return']} | 有20日收益: {s['has_20d_return']}",
        "",
        "## 标签分布",
        "",
    ]
    for label, cnt in s["label_distribution"].items():
        lines.append(f"- {label}: {cnt}")
    lines += ["", "## 按标签统计（胜率 = 正收益占比）", "",
              "| 标签 | 样本数 | 5日均值 | 5日胜率 | 20日均值 | 20日胜率 |",
              "|------|--------|---------|---------|----------|----------|"]
    for label in ["强烈关注", "值得关注", "中性观察", "暂不参与"]:
        st = result["by_label"].get(label)
        if not st:
            continue
        lines.append(f"| {label} | {st['n']} | "
                     f"{_md(st['r5_mean'])} | {_md(st['r5_win'])} | "
                     f"{_md(st['r20_mean'])} | {_md(st['r20_win'])} |")
    lines += ["", "## 按评分分桶统计（10分一档）", "",
              "| 评分区间 | 样本数 | 5日均值 | 5日胜率 | 20日均值 | 20日胜率 |",
              "|----------|--------|---------|---------|----------|----------|"]
    for bucket in sorted(result["by_score_bucket"].keys()):
        st = result["by_score_bucket"][bucket]
        lines.append(f"| {bucket} | {st['n']} | "
                     f"{_md(st['r5_mean'])} | {_md(st['r5_win'])} | "
                     f"{_md(st['r20_mean'])} | {_md(st['r20_win'])} |")

    # 区分度结论：优先用分桶数据（样本更分散），再看标签组
    lines += ["", "## 区分度结论", ""]
    buckets = result["by_score_bucket"]
    # 取最高分桶 vs 最低分桶（样本≥3 的）
    valid = [(b, s) for b, s in buckets.items() if s["n"] >= 3 and s["r20_win"] is not None]
    if len(valid) >= 2:
        valid.sort(key=lambda x: int(x[0].split("-")[0]))
        low_b, low_s = valid[0]
        high_b, high_s = valid[-1]
        diff = high_s["r20_win"] - low_s["r20_win"]
        verdict = "✅ 有区分度" if diff > 5 else "⚠ 区分度不足"
        lines.append(f"最高分桶 **{high_b}** 20日胜率 **{high_s['r20_win']}%** (n={high_s['n']}) vs "
                     f"最低分桶 **{low_b}** **{low_s['r20_win']}%** (n={low_s['n']})，"
                     f"差值 **{diff:+.1f}%** → {verdict}")
        lines.append("")
        lines.append("> 注：评分越高胜率越高则体系有效。当前样本受限于测试库（6只股票/1年），"
                     "强烈关注组样本不足，待全股池数据补齐后需重新验证。")
    else:
        ex = result["by_label"].get("强烈关注", {})
        poor = result["by_label"].get("暂不参与", {})
        if ex.get("r20_win") and poor.get("r20_win"):
            diff = ex["r20_win"] - poor["r20_win"]
            verdict = "✅ 有区分度" if diff > 5 else "⚠ 区分度不足"
            lines.append(f"强烈关注 20日胜率 **{ex['r20_win']}%** vs 暂不参与 **{poor['r20_win']}%**，"
                         f"差值 **{diff:+.1f}%** → {verdict}")
        else:
            lines.append("样本不足，无法判断区分度（强烈关注/暂不参与组缺少 20 日收益数据）")

    lines += ["", "---", "",
              "**说明**",
              "- 收益率 = (N日后收盘价 - 信号日收盘价) / 信号日收盘价 × 100%",
              "- 胜率 = 正收益信号数 / 有效信号数 × 100%",
              "- 无分钟线数据时，分时维度按 50% 折算（设计 §12）",
              "- 设计 §11 验收标准：强烈关注组 20 日正收益占比应显著高于暂不参与组",
              ]

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def _md(v) -> str:
    """报告数值格式化（None → '-'）。"""
    return "-" if v is None else f"{v}%"
