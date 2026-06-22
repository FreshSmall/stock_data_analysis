"""
投资推荐评分引擎（recommender）

对股票从 4 个维度评分（各 0-100），加权得综合推荐分：
  - 价值分(30%): PE/PB/市值
  - 技术分(40%): 趋势/量价/MACD/RSI
  - 筹码分(30%): 获利比例/集中度/支撑位

综合分 = value*0.3 + technical*0.4 + chip*0.3
标签: 强烈推荐(80+) / 值得关注(65+) / 观察(50+) / 暂不建议(<50)
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd

from core.indicators import analyze, volume_engine


# ============ §1 价值分 ============

def score_value(pe: float, pb: float, total_mv: float) -> tuple:
    """价值分（满分 100）。

    PE 5-15 低估 +40 | 15-25 合理 +25 | 25-40 偏高 +10 | 亏损 0
    PB <1.5 低估 +30 | 1.5-3 合理 +20 | 3-5 偏高 +10 | >5 高估 0
    市值 >200亿 +30 | 50-200亿 +20 | <50亿 +10
    """
    score = 0
    reasons = []

    # PE
    if pe is None or pe <= 0:
        reasons.append("PE 亏损或缺失")
    elif pe <= 15:
        score += 40; reasons.append(f"PE {pe:.1f} 低估")
    elif pe <= 25:
        score += 25; reasons.append(f"PE {pe:.1f} 合理")
    elif pe <= 40:
        score += 10; reasons.append(f"PE {pe:.1f} 偏高")
    else:
        reasons.append(f"PE {pe:.1f} 高估")

    # PB
    if pb is None or pb <= 0:
        pass
    elif pb < 1.5:
        score += 30; reasons.append(f"PB {pb:.2f} 低估")
    elif pb < 3:
        score += 20; reasons.append(f"PB {pb:.2f} 合理")
    elif pb < 5:
        score += 10
    else:
        reasons.append(f"PB {pb:.2f} 高估")

    # 市值
    if total_mv:
        if total_mv > 200:
            score += 30; reasons.append(f"市值 {total_mv:.0f}亿 大盘")
        elif total_mv > 50:
            score += 20
        else:
            score += 10; reasons.append(f"市值 {total_mv:.0f}亿 小盘")

    return min(score, 100), reasons


# ============ §2 技术分 ============

def score_technical(df: pd.DataFrame) -> tuple:
    """技术分（满分 100），需要日线 DataFrame。

    MA20 上行 +30 | MACD 多头 +25 | RSI 40-70 +20 | 量比>1 +25
    RSI>80 超买 -15 | RSI<20 超卖 -10
    """
    if df is None or len(df) < 30:
        return 50, ["日线数据不足"]

    score = 0
    reasons = []
    df = analyze.calc_ma(df)
    df = analyze.calc_rsi(df)
    df = analyze.calc_macd(df)
    vol = volume_engine.analyze_volume_daily(df)

    last = df.iloc[-1]
    close = float(last["close"])

    # MA20 趋势
    ma20 = last.get("ma20")
    if ma20 and not pd.isna(ma20):
        if close > float(ma20):
            # 判断 MA20 是否上行（近 5 日）
            recent_ma = df["ma20"].dropna().tail(5)
            if len(recent_ma) >= 2 and recent_ma.iloc[-1] > recent_ma.iloc[0]:
                score += 30; reasons.append("MA20 上行，价格站上均线")
            else:
                score += 15; reasons.append("价格站上 MA20")
        else:
            reasons.append("价格低于 MA20")

    # MACD
    macd_hist = last.get("macd_hist")
    macd_signal = "多头" if macd_hist and float(macd_hist) > 0 else "空头"
    if macd_signal == "多头":
        score += 25; reasons.append("MACD 多头")
    else:
        reasons.append("MACD 空头")

    # RSI
    rsi = last.get("rsi")
    if rsi and not pd.isna(rsi):
        rsi = float(rsi)
        if 40 <= rsi <= 70:
            score += 20; reasons.append(f"RSI {rsi:.0f} 健康区间")
        elif rsi > 80:
            score -= 15; reasons.append(f"RSI {rsi:.0f} 超买")
        elif rsi < 20:
            score -= 10; reasons.append(f"RSI {rsi:.0f} 超卖")
        else:
            reasons.append(f"RSI {rsi:.0f}")

    # 量比
    vol_ratio = vol.get("vol_ratio")
    if vol_ratio and float(vol_ratio) > 1.0:
        score += 25; reasons.append(f"量比 {vol_ratio:.1f} 放量")
    elif vol_ratio and float(vol_ratio) > 0.5:
        score += 10

    return max(0, min(score, 100)), reasons, {
        "ma20_trend": "上行" if score >= 15 and ma20 else "下行",
        "macd_signal": macd_signal,
        "rsi_value": round(rsi, 1) if rsi and not pd.isna(rsi) else None,
        "vol_ratio": round(float(vol_ratio), 2) if vol_ratio else None,
    }


# ============ §3 筹码分 ============

def score_chip(chip: Optional[dict], close: float) -> tuple:
    """筹码分（满分 100）。

    获利比例 <30% +40 | 30-50% +20 | 50-85% +10 | >85% 0(扣5)
    集中度 <15% +30 | 15-25% +15 | >25% +5
    价格接近 90% 下沿(支撑) +30 | 接近上沿(阻力) 0
    """
    if not chip:
        return 50, ["无筹码数据"]

    score = 0
    reasons = []
    profit = chip.get("profit_ratio")
    conc = chip.get("concentration_90")
    cost_low = chip.get("cost_90_low")
    cost_high = chip.get("cost_90_high")

    # 获利比例
    if profit is not None:
        profit = float(profit)
        if profit < 0.30:
            score += 40; reasons.append(f"获利盘仅 {profit*100:.0f}%，套牢压力小")
        elif profit < 0.50:
            score += 20; reasons.append(f"获利盘 {profit*100:.0f}%")
        elif profit < 0.85:
            score += 10
        else:
            score -= 5; reasons.append(f"获利盘 {profit*100:.0f}% 堆积")

    # 集中度
    if conc is not None:
        conc = float(conc)
        if conc < 0.15:
            score += 30; reasons.append(f"集中度 {conc*100:.1f}% 高度集中")
        elif conc < 0.25:
            score += 15
        else:
            score += 5; reasons.append(f"集中度 {conc*100:.1f}% 分散")

    # 支撑/阻力
    if close and cost_low and cost_high:
        cost_low, cost_high = float(cost_low), float(cost_high)
        band = cost_high - cost_low
        if band > 0:
            pos = (close - cost_low) / band  # 0=下沿, 1=上沿
            if pos < 0.3:
                score += 30; reasons.append("价格接近筹码支撑位")
            elif pos > 0.8:
                reasons.append("价格接近筹码阻力位")

    return max(0, min(score, 100)), reasons


# ============ §4 综合推荐分 ============

W_VALUE = 0.3
W_TECHNICAL = 0.4
W_CHIP = 0.3


def recommend_label(score: float) -> str:
    if score >= 80: return "强烈推荐"
    if score >= 65: return "值得关注"
    if score >= 50: return "观察"
    return "暂不建议"


def score_stock_recommendation(stock_code: str, stock_name: str,
                                daily_df: pd.DataFrame,
                                pool_info: dict,
                                chip: Optional[dict] = None) -> dict:
    """对单只股票计算完整推荐评分。

    返回包含 4 维分数 + 标签 + 理由 + 各指标快照的 dict（可直接入库）。
    """
    close = float(daily_df.iloc[-1]["close"]) if daily_df is not None and len(daily_df) else 0

    v_score, v_reasons = score_value(
        pool_info.get("pe"), pool_info.get("pb"), pool_info.get("total_mv"))
    t_score, t_reasons, tech_indicators = score_technical(daily_df)
    c_score, c_reasons = score_chip(chip, close)

    recommend = round(v_score * W_VALUE + t_score * W_TECHNICAL + c_score * W_CHIP, 1)
    label = recommend_label(recommend)
    reasons = v_reasons + t_reasons + c_reasons

    return {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "exchange": pool_info.get("exchange"),
        "value_score": round(v_score, 1),
        "technical_score": round(t_score, 1),
        "chip_score": round(c_score, 1),
        "recommend_score": recommend,
        "label": label,
        "reasons": json.dumps(reasons, ensure_ascii=False),
        # 基础指标
        "total_mv": pool_info.get("total_mv"),
        "pe": pool_info.get("pe"),
        "pb": pool_info.get("pb"),
        "pct_change": pool_info.get("pct_change"),
        "turnover": pool_info.get("turnover"),
        "industry": pool_info.get("industry"),
        # 技术指标
        "ma20_trend": tech_indicators.get("ma20_trend"),
        "macd_signal": tech_indicators.get("macd_signal"),
        "rsi_value": tech_indicators.get("rsi_value"),
        "vol_ratio": tech_indicators.get("vol_ratio"),
        # 筹码指标
        "chip_profit_ratio": chip.get("profit_ratio") if chip else None,
        "chip_concentration": chip.get("concentration_90") if chip else None,
    }
