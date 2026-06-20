"""
量化策略筛选器 — 针对波段周期(1-4周)的 4 种选股策略

设计目标：从全股池中按特定策略筛选股票，辅助波段交易决策。

策略:
  1. trend_following  趋势跟踪：顺势持有，捕捉上升趋势
  2. breakout         突破信号：突破20日高点入场
  3. pullback_buy     回调买入：上升趋势中缩量回踩均线
  4. momentum_rank    动量排名：近期涨幅最强

依赖: analyze.py(MA/RSI/MACD) + volume_engine.py(量价指标)
"""
from datetime import date
from typing import Optional

import pandas as pd

import analyze
import volume_engine
from db import query_daily


# ============ 策略 1：趋势跟踪 ============

def screen_trend_following(df: pd.DataFrame) -> Optional[dict]:
    """趋势跟踪策略：捕捉处于上升通道的股票。

    条件（全部满足）:
      - MA20 上行（今日 MA20 > 5日前 MA20）
      - 收盘价站上 MA20
      - MACD 红柱（DIF > DEA）
      - RSI 在 40-70 健康区间（非超买）

    返回: {'match': bool, 'score': 0-100, 'reason': str} 或 None（数据不足）
    """
    if df is None or len(df) < 30:
        return None

    df = analyze.calc_ma(df)
    df = analyze.calc_macd(df)
    df = analyze.calc_rsi(df)
    last = df.iloc[-1]

    ma20_now = float(last["ma20"])
    ma20_5d_ago = float(df["ma20"].iloc[-6]) if len(df) >= 6 else ma20_now
    ma20_rising = ma20_now > ma20_5d_ago
    price_above_ma20 = float(last["close"]) > ma20_now
    macd_bull = float(last["dif"]) > float(last["dea"])
    rsi = float(last["rsi"])
    rsi_healthy = 40 <= rsi <= 70

    conditions = [ma20_rising, price_above_ma20, macd_bull, rsi_healthy]
    score = sum(conditions) / 4 * 100

    parts = []
    if ma20_rising:
        parts.append("MA20上行")
    if price_above_ma20:
        parts.append("价格站上MA20")
    if macd_bull:
        parts.append("MACD多头")
    if rsi_healthy:
        parts.append(f"RSI{rsi:.0f}健康")
    elif rsi > 70:
        parts.append(f"RSI{rsi:.0f}超买")
    else:
        parts.append(f"RSI{rsi:.0f}偏弱")

    return {
        "match": all(conditions),
        "score": round(score, 1),
        "reason": "趋势跟踪：" + "，".join(parts),
    }


# ============ 策略 2：突破信号 ============

def screen_breakout(df: pd.DataFrame) -> Optional[dict]:
    """突破策略：价格突破近期高点，配合放量。

    条件:
      - 收盘价突破过去20日最高价（不含当日）
      - 量比 > 1.5（放量确认）
      - 非 60 日新高（排除已涨太多的，避免追高）

    返回: dict 或 None
    """
    if df is None or len(df) < 25:
        return None

    df = df.reset_index(drop=True)
    last = df.iloc[-1]
    close = float(last["close"])
    high_20d = float(df["high"].iloc[-21:-1].max())
    high_60d = float(df["high"].iloc[-61:-1].max()) if len(df) >= 61 else float("inf")

    vol = volume_engine.analyze_volume_daily(df)
    vol_ratio = vol.get("vol_ratio")

    breakout_20d = close > high_20d
    not_overbought = close <= high_60d * 1.1  # 不超过60日高点10%
    volume_confirm = vol_ratio is not None and vol_ratio > 1.5

    conditions = [breakout_20d, volume_confirm, not_overbought]
    score = sum(conditions) / 3 * 100

    parts = []
    if breakout_20d:
        parts.append(f"突破20日新高({high_20d:.2f})")
    if volume_confirm:
        parts.append(f"放量(量比{vol_ratio:.1f})")
    if not_overbought:
        parts.append("未过度拉升")
    else:
        parts.append("⚠ 接近60日高点")

    return {
        "match": breakout_20d and volume_confirm,
        "score": round(score, 1),
        "reason": "突破信号：" + "，".join(parts),
    }


# ============ 策略 3：回调买入 ============

def screen_pullback_buy(df: pd.DataFrame) -> Optional[dict]:
    """回调买入策略：上升趋势中缩量回踩均线。

    条件:
      - 大趋势向上（MA20 > MA60，中期多头）
      - 短期回调（近3日下跌或横盘）
      - 缩量（量比 < 0.8）
      - 回踩 MA10 或 MA20 附近（价格在均线 ±2% 内）

    返回: dict 或 None
    """
    if df is None or len(df) < 65:
        return None

    df = analyze.calc_ma(df)
    df = df.reset_index(drop=True)
    last = df.iloc[-1]
    close = float(last["close"])
    ma10 = float(last["ma10"])
    ma20 = float(last["ma20"])
    ma60 = float(last["ma60"])

    # 大趋势向上
    trend_up = ma20 > ma60
    # 近3日回调
    recent_3d = df["close"].iloc[-4:]
    pulling_back = float(recent_3d.iloc[-1]) < float(recent_3d.iloc[0]) * 1.01

    vol = volume_engine.analyze_volume_daily(df)
    vol_ratio = vol.get("vol_ratio")
    shrinking = vol_ratio is not None and vol_ratio < 0.8

    # 回踩均线（价格在 MA10 或 MA20 的 ±2% 内）
    near_ma10 = abs(close - ma10) / ma10 <= 0.02 if ma10 > 0 else False
    near_ma20 = abs(close - ma20) / ma20 <= 0.02 if ma20 > 0 else False
    at_support = near_ma10 or near_ma20

    conditions = [trend_up, pulling_back, shrinking, at_support]
    score = sum(conditions) / 4 * 100

    parts = []
    if trend_up:
        parts.append("中期多头(MA20>MA60)")
    if pulling_back:
        parts.append("短线回调")
    if shrinking:
        parts.append(f"缩量(量比{vol_ratio:.1f})")
    if at_support:
        support = "MA10" if near_ma10 else "MA20"
        parts.append(f"回踩{support}")

    return {
        "match": trend_up and pulling_back and at_support,
        "score": round(score, 1),
        "reason": "回调买入：" + "，".join(parts),
    }


# ============ 策略 4：动量排名 ============

def screen_momentum(df: pd.DataFrame) -> Optional[dict]:
    """动量策略：近期涨幅排名靠前（需配合 run_screener 的排名使用）。

    条件:
      - 近20日涨幅 > 5%
      - RSI 50-70（强势但未超买）
      - 成交量放大（量比 > 1）

    返回: dict 或 None（含 return_20d 字段供排名）
    """
    if df is None or len(df) < 25:
        return None

    df = analyze.calc_rsi(df)
    df = df.reset_index(drop=True)
    close_now = float(df["close"].iloc[-1])
    close_20d_ago = float(df["close"].iloc[-21])
    return_20d = (close_now - close_20d_ago) / close_20d_ago * 100

    rsi = float(df["rsi"].iloc[-1])
    vol = volume_engine.analyze_volume_daily(df)
    vol_ratio = vol.get("vol_ratio")

    strong = return_20d > 5
    rsi_ok = 50 <= rsi <= 70
    vol_ok = vol_ratio is not None and vol_ratio > 1

    conditions = [strong, rsi_ok, vol_ok]
    score = sum(conditions) / 3 * 100

    parts = [f"20日涨{return_20d:+.1f}%"]
    if rsi_ok:
        parts.append(f"RSI{rsi:.0f}强势")
    elif rsi > 70:
        parts.append(f"RSI{rsi:.0f}超买")
    if vol_ok:
        parts.append(f"放量(量比{vol_ratio:.1f})")

    return {
        "match": strong and rsi_ok,
        "score": round(score, 1),
        "return_20d": round(return_20d, 2),
        "reason": "动量强势：" + "，".join(parts),
    }


# ============ 统一执行入口 ============

STRATEGIES = {
    "trend": ("趋势跟踪", screen_trend_following),
    "breakout": ("突破信号", screen_breakout),
    "pullback": ("回调买入", screen_pullback_buy),
    "momentum": ("动量排名", screen_momentum),
}


def _extract_indicators(df: pd.DataFrame) -> dict:
    """从日线 DataFrame 统一提取前端表格所需的指标字段。
    与 stock_signal 表字段名对齐，便于前端复用渲染逻辑。"""
    out = {
        "vol_ratio": None, "vol_price_trend": None,
        "macd_signal": None, "rsi_value": None,
        "vwap_deviation": None,
    }
    try:
        # 量价指标
        vol = volume_engine.analyze_volume_daily(df)
        out["vol_ratio"] = vol.get("vol_ratio")
        out["vol_price_trend"] = vol.get("vol_price_trend")

        # MACD 信号标签
        df2 = analyze.calc_macd(df)
        last = df2.iloc[-1]
        if float(last["dif"]) > float(last["dea"]):
            # 判断是否当日金叉
            prev = df2.iloc[-2] if len(df2) >= 2 else last
            out["macd_signal"] = "金叉" if float(prev["dif"]) <= float(prev["dea"]) else "红柱"
        else:
            prev = df2.iloc[-2] if len(df2) >= 2 else last
            out["macd_signal"] = "死叉" if float(prev["dif"]) >= float(prev["dea"]) else "绿柱"

        # RSI
        df2 = analyze.calc_rsi(df2)
        rsi = df2["rsi"].iloc[-1]
        out["rsi_value"] = float(rsi) if pd.notna(rsi) else None

        # VWAP 偏离（日线用当日 close vs 当日典型价格近似，无分钟线则 None）
        out["vwap_deviation"] = None
    except Exception:
        pass
    return out


def _fetch_stock_names(stock_codes: list) -> dict:
    """批量从股池表取股票名称，返回 {code: name}。"""
    if not stock_codes:
        return {}
    from db import get_engine
    from sqlalchemy import text
    from pandas import read_sql
    engine = get_engine()
    out = {}
    batch_size = 500
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ",".join(f":c{j}" for j in range(len(batch)))
        params = {f"c{j}": c for j, c in enumerate(batch)}
        df = read_sql(text(
            f"SELECT stock_code, stock_name FROM stock_pool "
            f"WHERE stock_code IN ({placeholders}) "
            f"AND trade_date = (SELECT MAX(trade_date) FROM stock_pool)"
        ), engine, params=params)
        for _, row in df.iterrows():
            if row["stock_name"]:
                out[row["stock_code"]] = row["stock_name"]
    return out


def run_screener(strategy: str, stock_codes: list,
                 top_n: int = 50, signal_date=None) -> dict:
    """运行指定策略筛选。

    参数:
      strategy: 'trend' / 'breakout' / 'pullback' / 'momentum'
      stock_codes: 待筛选的股票代码列表
      top_n: 返回前 N 只（按 score 降序）
      signal_date: 不使用（保持接口一致）

    返回: {'strategy', 'strategy_name', 'total', 'matched', 'results': list}
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"未知策略: {strategy}，可选: {list(STRATEGIES.keys())}")

    strategy_name, screen_fn = STRATEGIES[strategy]

    # 批量预取日线数据（复用 signal_scorer 的批量预取逻辑）
    from signal_scorer import _bulk_fetch_daily
    daily_map = _bulk_fetch_daily(stock_codes)

    # 批量取股票名称（从股池表）
    name_map = _fetch_stock_names(stock_codes)

    results = []
    for code in stock_codes:
        df = daily_map.get(code)
        if df is None or df.empty:
            continue
        try:
            r = screen_fn(df)
        except Exception:
            continue
        if r is None:
            continue
        r["stock_code"] = code
        r["stock_name"] = name_map.get(code)
        # 统一补充指标字段（供前端表格展示）
        r.update(_extract_indicators(df))
        results.append(r)

    # 动量策略额外按 return_20d 排序
    if strategy == "momentum":
        results.sort(key=lambda x: x.get("return_20d", 0), reverse=True)
    else:
        results.sort(key=lambda x: x["score"], reverse=True)

    matched = [r for r in results if r["match"]]
    top = (matched if matched else results)[:top_n]

    return {
        "strategy": strategy,
        "strategy_name": strategy_name,
        "total": len(stock_codes),
        "scanned": len(results),
        "matched": len(matched),
        "results": top,
    }
