"""
综合信号评分器 — 汇总量价 + 价格 + 分时，输出评分/标签/理由

设计文档: spec/volume-analysis/2026-06-17-volume-analysis-system-design.md
  - §3.4 权重表（默认 0.30/0.25/0.20/0.15/0.10）
  - §8.1-§8.5 五维计分表（满分 100）
  - §8.6 标签映射（强烈关注/值得关注/中性观察/暂不参与）
  - §12 风险：分时数据缺失按 50% 折算；涨停（pct_change≥9.8%）扣分

外部依赖: analyze.py(MA/RSI/MACD/金叉) + volume_engine.py(量价/异动/分时)
"""
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text

from core.indicators import analyze, volume_engine
from config import (
    SIGNAL_MIN_SCORE, SIGNAL_W_VOL_PRICE, SIGNAL_W_TREND,
    SIGNAL_W_MOMENTUM, SIGNAL_W_ANOMALY, SIGNAL_W_INTRADAY,
)
from data.db import query_daily, query_minute, query_chip_latest, get_engine


# 涨跌停判定阈值（pct_change%）
LIMIT_UP_THRESHOLD = 9.8

# 涨停扣分
LIMIT_UP_PENALTY = 5

# 筹码调整分阈值（chip_bonus 上限 ±5）
CHIP_BONUS_LOCKED = 5        # 筹码锁定（低获利+高集中）：+5
CHIP_BONUS_CONVERGE = 2      # 筹码收敛：+2
CHIP_PENALTY_HEAVY = -5      # 获利盘堆积（顶部压力）：-5


# ============ §8.1 量价配合（满分30） ============

def _score_vol_price(ind: dict) -> float:
    """量价同向10 / 量比8 / MAVOL5v10 6 / 放量突破4 / 缩量回踩2"""
    score = 0.0

    # 量价同向 (10)
    trend = ind.get("vol_price_trend", "中性")
    if trend == "同向多":
        score += 10
    elif trend == "同向空":
        score += 7
    elif trend in ("顶背离", "底背离"):
        score += 3
    # 中性 0

    # 量比 (8)
    ratio = ind.get("vol_ratio")
    if ratio is not None:
        if ratio > 2.0:
            score += 8
        elif ratio >= 1.5:
            score += 6
        elif ratio >= 1.0:
            score += 4
        elif ratio >= 0.5:
            score += 3
        else:
            score += 2

    # MAVOL5 vs MAVOL10 (6)
    m5 = ind.get("mavol5")
    m10 = ind.get("mavol10")
    if m5 is not None and m10 is not None and m10 > 0:
        m5_prev = ind.get("mavol5_prev")
        m10_prev = ind.get("mavol10_prev")
        crossed = (m5_prev is not None and m10_prev is not None
                   and m5 > m10 and m5_prev <= m10_prev)
        if crossed:
            score += 6
        elif m5 > m10:
            score += 4
        else:
            score += 2

    # 放量突破 (4)
    if ind.get("breakout"):
        score += 4

    # 缩量回踩 (2)
    if ind.get("pullback"):
        score += 2

    return score


# ============ §8.2 趋势方向（满分25） ============

def _score_trend(ind: dict) -> float:
    """MA排列10 / MA5斜率5 / MACD柱5 / 乖离5"""
    score = 0.0

    ma5 = ind.get("ma5")
    ma10 = ind.get("ma10")
    ma20 = ind.get("ma20")
    ma60 = ind.get("ma60")
    close = ind.get("close")

    # MA 多空排列 (10)
    if all(v is not None for v in (ma5, ma10, ma20, ma60)):
        if ma5 > ma10 > ma20 > ma60:        # 完整多头
            score += 10
        elif ma5 > ma10 > ma20:             # 3 连多
            score += 7
        elif ma5 > ma10:                    # 2 连多
            score += 5
        elif ma5 < ma10 < ma20 < ma60:      # 完整空头
            score += 0
        elif ma5 < ma10 < ma20:             # 空头趋势
            score += 1
        else:                               # 缠绕
            score += 3

    # MA5 斜率 (5)
    ma5_prev = ind.get("ma5_prev")
    if ma5 is not None and ma5_prev is not None and ma5_prev > 0:
        slope_pct = (ma5 - ma5_prev) / ma5_prev * 100
        if slope_pct > 1:
            score += 5
        elif slope_pct > 0:
            score += 3
        elif abs(slope_pct) < 1e-6:
            score += 2
        # 下行 0

    # MACD 柱状图 (5)
    hist = ind.get("macd_hist")
    hist_prev = ind.get("macd_hist_prev")
    if hist is not None:
        if hist > 0 and hist_prev is not None and hist > hist_prev:
            score += 5    # 红柱放大
        elif hist > 0:
            score += 4    # 红柱
        elif hist < 0 and hist_prev is not None and hist > hist_prev:
            score += 2    # 绿柱缩小
        # 绿柱 0

    # 均线乖离 (5)：close vs MA20
    if close is not None and ma20 is not None and ma20 > 0:
        dev = (close - ma20) / ma20 * 100
        if close > ma20:
            if dev < 10:
                score += 5
            elif dev <= 20:
                score += 3
            else:
                score += 1
        else:
            score += 2

    return score


# ============ §8.3 动量信号（满分20） ============

def _score_momentum(ind: dict) -> float:
    """RSI 8 / MACD金叉6 / MA金叉4 / VR 2"""
    score = 0.0

    # RSI 区间 (8)
    rsi = ind.get("rsi")
    if rsi is not None:
        if 40 <= rsi <= 60:
            score += 8
        elif 30 <= rsi < 40:
            score += 6
        elif 60 < rsi <= 70:
            score += 5
        elif rsi < 30:
            score += 4    # 超卖反弹预期
        else:             # >70 超买
            score += 2

    # MACD 金叉 (6)
    if ind.get("macd_golden"):
        score += 6
    elif ind.get("macd_above"):
        days = ind.get("macd_above_days", 10)
        if days <= 5:
            score += 4
        else:
            score += 2

    # MA 金叉 (4)
    if ind.get("ma_golden"):
        score += 4

    # VR 容量比率 (2)
    vr = ind.get("vr")
    if vr is not None:
        if 80 <= vr <= 160:
            score += 2
        elif vr < 40:
            score += 1    # 过冷，可能底部
        # >200 过热 0；其他 0

    return score


# ============ §8.4 异动检测（满分15） ============

def _score_anomaly(ind: dict) -> float:
    """Z-Score 6 / 换手率突增5 / 尾盘集中度4"""
    score = 0.0

    # Z-Score (6)
    z = ind.get("vol_zscore")
    if z is not None:
        az = abs(z)
        if az > 3:
            score += 6
        elif az > 2:
            score += 4
        elif az > 1:
            score += 2
        else:
            score += 1

    # 换手率突增 (5)
    spike = ind.get("turnover_spike")
    if spike is not None:
        if spike > 3:
            score += 5
        elif spike > 2:
            score += 4
        elif spike > 1.5:
            score += 2
        else:
            score += 1

    # 尾盘集中度 (4)
    tail = ind.get("tail_concentration")
    if tail is not None:
        if 25 <= tail <= 35:
            score += 4
        elif tail > 35:
            score += 3
        elif tail < 20:
            score += 2
        else:
            score += 1

    return score


# ============ §8.5 分时确认（满分10） ============

def _score_intraday(ind: dict) -> float:
    """VWAP偏离4 / 小时段分布4 / 分时连续性2"""
    score = 0.0

    # VWAP 偏离 (4)
    dev = ind.get("vwap_deviation")
    if dev is not None:
        if ind.get("close_above_vwap", True):
            if dev < 2:
                score += 4
            elif dev <= 4:
                score += 3
            else:
                score += 1
        else:
            score += 2

    # 小时段分布 (4)
    pattern = ind.get("hour_pattern", "均匀")
    pattern_score = {"早盘+午后双峰": 4, "午后放量": 3,
                     "早盘脉冲": 2, "均匀": 2, "尾盘异常": 1}
    score += pattern_score.get(pattern, 2)

    # 分时连续性 (2)
    cont = ind.get("intraday_continuity", "稳定")
    if cont == "逐步放大":
        score += 2
    elif cont == "稳定":
        score += 1
    # 脉冲后萎缩 0

    return score


# ============ 筹码维度（独立调整分，不改变五维权重）============

def _score_chip(chip: Optional[dict]) -> tuple:
    """根据筹码指标返回 (bonus, label)。

    筹码数据缺失返回 (0, '')，不影响主评分。
    逻辑:
      - 获利比例 < 0.30 且 集中度 < 0.15: 筹码锁定 → +5（套牢压力小+集中度高，潜在底部）
      - 获利比例 < 0.50 且 集中度 < 0.20: 筹码收敛 → +2（上方压力较轻）
      - 获利比例 > 0.85:                   获利盘堆积 → -5（顶部压力区）
      - 其它:                              中性 → 0
    """
    if not chip:
        return 0.0, ""
    profit = chip.get("profit_ratio")
    conc = chip.get("concentration_90")
    if profit is None or conc is None:
        return 0.0, ""

    import core.scoring.chip_engine
    avg_cost = chip.get("avg_cost") or 0
    close = chip.get("_close") or avg_cost or 0
    label, _ = chip_engine.chip_signal_label(profit, conc, avg_cost, close)

    if label == "筹码锁定":
        return CHIP_BONUS_LOCKED, label
    if label == "筹码收敛":
        return CHIP_BONUS_CONVERGE, label
    if label == "获利盘堆积":
        return CHIP_PENALTY_HEAVY, label
    return 0.0, label


# ============ §8.6 标签映射 ============

def map_label(score: float) -> tuple:
    """总分 → (标签, 建议动作)。分数会被 clamp 到 [0, 100]。"""
    s = max(0, min(100, score))
    if s >= 80:
        return "强烈关注", "关注"
    if s >= 65:
        return "值得关注", "观察"
    if s >= 50:
        return "中性观察", "无"
    return "暂不参与", "回避"


# ============ 指标聚合 + 评分编排 ============

def _classify_hour_pattern(hour_dist: dict) -> tuple:
    """根据小时段分布 → (pattern, continuity)
    pattern: 早盘+午后双峰 / 午后放量 / 早盘脉冲 / 均匀 / 尾盘异常
    continuity: 逐步放大 / 稳定 / 脉冲后萎缩"""
    if not hour_dist:
        return "均匀", "稳定"
    slots = ["09:30-10:30", "10:30-11:30", "13:00-14:00", "14:00-15:00"]
    vals = [hour_dist.get(s, 0) for s in slots]
    morn, late_morn, early_pm, late_pm = vals
    total = sum(vals) or 1

    # 尾盘占比
    if late_pm / total > 0.4:
        return "尾盘异常", "脉冲后萎缩" if morn / total > 0.3 else "逐步放大"
    # 双峰
    if morn / total > 0.25 and late_pm / total > 0.25:
        return "早盘+午后双峰", "逐步放大"
    # 午后放量
    if (early_pm + late_pm) / total > 0.55:
        return "午后放量", "逐步放大"
    # 早盘脉冲
    if morn / total > 0.4:
        return "早盘脉冲", "脉冲后萎缩"
    return "均匀", "稳定"


def score_stock(stock_code: str, signal_date: Optional[date] = None,
                daily_df: pd.DataFrame = None,
                minute_df: pd.DataFrame = None) -> Optional[dict]:
    """对单只股票计算综合评分。

    参数:
      stock_code:   股票代码
      signal_date:  信号日期（None=日线最新交易日）
      daily_df:     可选，预取的日线 DataFrame（避免重复查 DB）
      minute_df:    可选，预取的当日分钟线 DataFrame

    返回对应 stock_signal 表的完整记录 dict；当日无日线数据返回 None。
    """
    if daily_df is not None:
        df = daily_df.copy()
    else:
        df = query_daily(stock_code, limit=250)
    if df.empty:
        return None
    df = df.reset_index(drop=True)

    # —— 价格指标（复用 analyze.py） ——
    df = analyze.calc_ma(df)
    df = analyze.calc_rsi(df)
    df = analyze.calc_macd(df)
    last = df.iloc[-1]

    # signal_date 默认取最新交易日
    if signal_date is None:
        signal_date = last["trade_date"]

    # 涨停判定
    pct = float(last.get("pct_change") or 0)
    limit_up = pct >= LIMIT_UP_THRESHOLD

    # —— 量价分析（volume_engine） ——
    vol_daily = volume_engine.analyze_volume_daily(df)
    # 异动（含可选分钟数据）
    if minute_df is None:
        try:
            minute_df = query_minute(stock_code, date_str=str(signal_date))
        except Exception:
            minute_df = None
    anomaly = volume_engine.detect_volume_anomaly(df, minute_df=minute_df)
    intraday = volume_engine.analyze_volume_minute(minute_df) if minute_df is not None and not minute_df.empty else {}

    # —— 信号检测（金叉） ——
    macd_above = bool(last["dif"] > last["dea"])
    macd_above_days = 0
    if macd_above:
        # 数 DIF>DEA 连续天数
        dif = df["dif"].astype(float)
        dea = df["dea"].astype(float)
        n = 0
        for i in range(len(df) - 1, -1, -1):
            if dif.iloc[i] > dea.iloc[i]:
                n += 1
            else:
                break
        macd_above_days = n
    macd_golden = macd_above_days == 1
    ma_golden = bool(last["ma5"] > last["ma20"]
                     and df["ma5"].iloc[-2] <= df["ma20"].iloc[-2])

    # —— 聚合 ind dict（喂给 _score_*） ——
    close_above_vwap = (intraday.get("vwap_deviation") is not None
                        and intraday.get("vwap_deviation") >= 0)
    hour_pattern, intraday_cont = _classify_hour_pattern(intraday.get("hour_distribution", {}))

    ind = {
        # 量价
        "vol_ratio": vol_daily["vol_ratio"],
        "mavol5": vol_daily["mavol5"], "mavol10": vol_daily["mavol10"],
        "mavol5_prev": (df["volume"].astype(float).rolling(5).mean().iloc[-2]
                        if len(df) >= 6 else None),
        "mavol10_prev": (df["volume"].astype(float).rolling(10).mean().iloc[-2]
                         if len(df) >= 11 else None),
        "vol_price_trend": vol_daily["vol_price_trend"],
        "breakout": vol_daily["breakout"] or False,
        "pullback": vol_daily["pullback"] or False,
        # 趋势
        "ma5": float(last["ma5"]) if pd.notna(last["ma5"]) else None,
        "ma10": float(last["ma10"]) if pd.notna(last["ma10"]) else None,
        "ma20": float(last["ma20"]) if pd.notna(last["ma20"]) else None,
        "ma60": float(last["ma60"]) if pd.notna(last["ma60"]) else None,
        "ma5_prev": float(df["ma5"].iloc[-2]) if pd.notna(df["ma5"].iloc[-2]) else None,
        "close": float(last["close"]),
        "macd_hist": float(last["macd"]),
        "macd_hist_prev": float(df["macd"].iloc[-2]) if len(df) >= 2 else None,
        # 动量
        "rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else None,
        "macd_golden": macd_golden, "macd_above": macd_above,
        "macd_above_days": macd_above_days, "ma_golden": ma_golden,
        "vr": vol_daily["vr"],
        # 异动
        "vol_zscore": anomaly["vol_zscore"],
        "turnover_spike": anomaly["turnover_spike"],
        "tail_concentration": intraday.get("tail_concentration"),
        # 分时
        "vwap_deviation": intraday.get("vwap_deviation"),
        "close_above_vwap": close_above_vwap,
        "hour_pattern": hour_pattern,
        "intraday_continuity": intraday_cont,
        # 风险
        "limit_up": limit_up,
    }

    # —— 五维得分 ——
    s_vol_price = _score_vol_price(ind)
    s_trend = _score_trend(ind)
    s_momentum = _score_momentum(ind)
    s_anomaly = _score_anomaly(ind)
    s_intraday = _score_intraday(ind)

    # 分时数据缺失 → 按 50% 折算（§12 风险表）
    has_intraday = bool(intraday)
    if not has_intraday:
        s_intraday = s_intraday * 0.5

    # —— 加权（权重归一化后，按各维度满分比例折算为 0-100）——
    # _score_* 返回的是绝对分（量价0-30/趋势0-25/动量0-20/异动0-15/分时0-10）
    # 转为该维度得分率，再按权重加权 × 100
    rate_vol_price = s_vol_price / 30
    rate_trend = s_trend / 25
    rate_momentum = s_momentum / 20
    rate_anomaly = s_anomaly / 15
    rate_intraday = s_intraday / 10
    total = round((rate_vol_price * SIGNAL_W_VOL_PRICE
                   + rate_trend * SIGNAL_W_TREND
                   + rate_momentum * SIGNAL_W_MOMENTUM
                   + rate_anomaly * SIGNAL_W_ANOMALY
                   + rate_intraday * SIGNAL_W_INTRADAY) * 100, 2)

    scores = {
        "vol_price": s_vol_price, "trend": s_trend, "momentum": s_momentum,
        "anomaly": s_anomaly, "intraday": s_intraday,
    }

    # —— 筹码维度（独立调整分，不改变五维权重）——
    # 优先使用 DB 已计算的最新筹码数据；缺失则在线计算
    chip = query_chip_latest(stock_code)
    if chip is None:
        try:
            import core.scoring.chip_engine
            chip = chip_engine.latest_chip_summary(df)
        except Exception:
            chip = None
    if chip:
        # 附带 close 供标签计算用
        chip = dict(chip)
        chip["_close"] = float(last["close"])
    chip_bonus, chip_label = _score_chip(chip)
    total = max(0, min(100, total + chip_bonus))

    # —— 涨停扣分 ——
    if limit_up:
        total = max(0, total - LIMIT_UP_PENALTY)

    label, action = map_label(total)
    reason = build_reason(scores, ind, chip_label=chip_label,
                          chip=chip, chip_bonus=chip_bonus)

    return {
        "signal_date": signal_date,
        "stock_code": stock_code,
        "stock_name": None,  # 由 runner 从股池补
        "score": total,
        "label": label,
        # 量价维度
        "vol_ratio": ind["vol_ratio"],
        "vol_zscore": ind["vol_zscore"],
        "vol_price_trend": ind["vol_price_trend"],
        "obv_signal": vol_daily["obv_signal"],
        "vr_value": ind["vr"],
        "breakout": int(bool(ind["breakout"])),
        "pullback": int(bool(ind["pullback"])),
        # 价格维度
        "ma_trend": _ma_trend_label(ind),
        "macd_signal": _macd_signal_label(ind),
        "rsi_value": ind["rsi"],
        "golden_cross": int(ma_golden),
        # 分时维度
        "vwap": intraday.get("vwap"),
        "vwap_deviation": ind["vwap_deviation"],
        "tail_concentration": ind["tail_concentration"],
        # 筹码维度
        "chip_profit_ratio": (chip or {}).get("profit_ratio"),
        "chip_concentration": (chip or {}).get("concentration_90"),
        "chip_avg_cost": (chip or {}).get("avg_cost"),
        "chip_label": chip_label or None,
        "chip_bonus": round(chip_bonus, 2),
        # 分项得分
        "score_vol_price": round(s_vol_price, 2),
        "score_trend": round(s_trend, 2),
        "score_momentum": round(s_momentum, 2),
        "score_anomaly": round(s_anomaly, 2),
        "score_intraday": round(s_intraday, 2),
        # 元数据
        "reason": reason,
    }


def _ma_trend_label(ind: dict) -> str:
    """MA 趋势标签：多头/空头/缠绕"""
    ma5, ma10, ma20, ma60 = (ind.get(k) for k in ("ma5", "ma10", "ma20", "ma60"))
    if any(v is None for v in (ma5, ma10, ma20, ma60)):
        return "缠绕"
    if ma5 > ma10 > ma20 > ma60:
        return "多头"
    if ma5 < ma10 < ma20 < ma60:
        return "空头"
    return "缠绕"


def _macd_signal_label(ind: dict) -> str:
    """MACD 信号标签：金叉/死叉/红柱/绿柱"""
    if ind.get("macd_golden"):
        return "金叉"
    hist = ind.get("macd_hist")
    if hist is None:
        return "绿柱"
    return "红柱" if hist > 0 else "绿柱"


def build_reason(scores: dict, ind: dict, chip_label: str = "",
                 chip: Optional[dict] = None, chip_bonus: float = 0.0) -> str:
    """根据分项得分和指标值，生成自然语言信号理由。"""
    parts = []

    # 量价
    if ind.get("breakout"):
        ratio = ind.get("vol_ratio")
        ratio_txt = f"量比{ratio:.1f}" if ratio else "放量"
        parts.append(f"放量突破20日高点({ratio_txt})")
    elif ind.get("pullback"):
        parts.append("缩量回踩均线")
    elif ind.get("vol_price_trend") == "同向多":
        parts.append("价涨量增格局延续")
    elif ind.get("vol_price_trend") in ("顶背离", "底背离"):
        parts.append(f"出现{ind['vol_price_trend']}，需警惕")

    # MAVOL 金叉
    if scores.get("vol_price", 0) >= 6 and ind.get("mavol5") and ind.get("mavol10"):
        if ind["mavol5"] > ind["mavol10"]:
            parts.append("MAVOL5 上穿 MAVOL10，量能放大")

    # 趋势
    trend_label = _ma_trend_label(ind)
    if trend_label == "多头":
        parts.append("MA 多头排列")
    elif trend_label == "空头":
        parts.append("MA 空头排列")

    # MACD
    if ind.get("macd_golden"):
        parts.append("MACD 金叉确认")
    elif ind.get("macd_hist") and ind["macd_hist"] > 0:
        parts.append("MACD 红柱")

    # 动量
    rsi = ind.get("rsi")
    if rsi is not None:
        if rsi < 30:
            parts.append(f"RSI {rsi:.0f} 超卖反弹预期")
        elif rsi > 70:
            parts.append(f"RSI {rsi:.0f} 超买")
        else:
            parts.append(f"RSI {rsi:.0f} 中性区间")

    # 异动
    tail = ind.get("tail_concentration")
    if tail and tail > 30:
        parts.append(f"尾盘资金集中度偏高({tail*100:.0f}%)")

    # 风险
    if ind.get("limit_up"):
        parts.append(f"⚠ 涨停风险：当日涨幅已达 {ind.get('pct_change', 0):.1f}%，注意追高风险")

    # 筹码
    if chip_label and chip:
        profit = chip.get("profit_ratio")
        conc = chip.get("concentration_90")
        if profit is not None and conc is not None:
            bonus_txt = f"（{chip_bonus:+.0f}分）" if chip_bonus else ""
            parts.append(f"{chip_label}：获利盘{profit*100:.0f}%、"
                         f"集中度{conc*100:.1f}%{bonus_txt}")

    return "，".join(parts) + ("。" if parts else "")


def score_batch(stock_codes: list, signal_date: Optional[date] = None) -> dict:
    """批量评分。返回 {'scored': list[dict], 'skipped': list[dict]}。
    跳过当日无数据/停牌；按 SIGNAL_MIN_SCORE 过滤；scored 按 score 降序。

    性能优化：一次性批量预取所有股票的 daily + minute 数据（避免 N 次单条查询）。
    """
    # —— 批量预取（显著降低 DB I/O）——
    daily_map = _bulk_fetch_daily(stock_codes)
    minute_map = _bulk_fetch_minute(stock_codes, signal_date)

    scored, skipped = [], []
    for code in stock_codes:
        df = daily_map.get(code)
        if df is None or df.empty:
            skipped.append({"stock_code": code, "reason": "当日无数据/停牌"})
            continue
        try:
            rec = score_stock(code, signal_date,
                              daily_df=df, minute_df=minute_map.get(code))
        except Exception as e:
            skipped.append({"stock_code": code, "reason": f"计算异常: {e}"})
            continue
        if rec is None:
            skipped.append({"stock_code": code, "reason": "当日无数据/停牌"})
            continue
        if rec["score"] < SIGNAL_MIN_SCORE:
            continue
        scored.append(rec)
    scored.sort(key=lambda r: r["score"], reverse=True)
    return {"scored": scored, "skipped": skipped}


def _bulk_fetch_daily(stock_codes: list) -> dict:
    """一次性批量预取股池股票的日线数据，返回 {stock_code: DataFrame}。
    只查股池中存在的股票（按 stock_code IN (...) 过滤），避免全表扫描。"""
    if not stock_codes:
        return {}
    engine = get_engine()
    # 分批避免 SQL IN 列表过长
    out = {}
    batch_size = 500
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ",".join(f":c{j}" for j in range(len(batch)))
        params = {f"c{j}": c for j, c in enumerate(batch)}
        sql = text(
            f"SELECT * FROM daily_prices "
            f"WHERE stock_code IN ({placeholders}) "
            f"ORDER BY stock_code, trade_date"
        )
        df_all = pd.read_sql(sql, engine, params=params)
        for code, grp in df_all.groupby("stock_code"):
            # 取最近 250 天
            grp = grp.sort_values("trade_date").tail(250).reset_index(drop=True)
            out[code] = grp
    return out


def _bulk_fetch_minute(stock_codes: list, signal_date) -> dict:
    """批量预取当日分钟线，返回 {stock_code: DataFrame}。无数据返回空 map。"""
    if not stock_codes or signal_date is None:
        return {}
    engine = get_engine()
    out = {}
    batch_size = 500
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ",".join(f":c{j}" for j in range(len(batch)))
        params = {f"c{j}": c for j, c in enumerate(batch)}
        params["dt"] = str(signal_date)
        sql = text(
            f"SELECT * FROM minute_prices "
            f"WHERE trade_date = :dt AND stock_code IN ({placeholders}) "
            f"ORDER BY stock_code, trade_time"
        )
        try:
            df_all = pd.read_sql(sql, engine, params=params)
        except Exception:
            continue
        for code, grp in df_all.groupby("stock_code"):
            out[code] = grp.sort_values("trade_time").reset_index(drop=True)
    return out
