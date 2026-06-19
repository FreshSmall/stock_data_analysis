"""
成交量分析引擎 — 量价关系(日线) / 量能异动 / 分时聚合

输入: 从 db.query_daily / query_minute 返回的 DataFrame
输出: 结构化 dict（字段对齐 stock_signal 表的量价/分时维度）

数据来源（无需新增拉取）:
  - daily_prices: volume / amount / turnover / close / high / low
  - minute_prices: trade_time(DATETIME) / volume / amount

设计文档: spec/volume-analysis/2026-06-17-volume-analysis-system-design.md §3.1 §3.2 §3.3
"""
from typing import Optional

import numpy as np
import pandas as pd


# ============ 日线量价关系分析（§3.1） ============

def analyze_volume_daily(df: pd.DataFrame) -> dict:
    """日线维度的成交量分析。

    输入: query_daily() 返回的 DataFrame（按 trade_date 升序，含 volume/close/high 等）
    输出: {
        'vol_ratio','vol_zscore','mavol5','mavol10','mavol20',
        'vol_price_trend','obv','obv_signal','vr','breakout','pullback',
    }
    数据不足时相关字段返回 None，不抛异常。
    """
    result = {
        "vol_ratio": None, "vol_zscore": None,
        "mavol5": None, "mavol10": None, "mavol20": None,
        "vol_price_trend": "中性",
        "obv": None, "obv_signal": "持平",
        "vr": None, "breakout": None, "pullback": None,
    }
    if df is None or df.empty or len(df) < 2:
        return result

    df = df.reset_index(drop=True)
    vol = df["volume"].astype(float)
    close = df["close"].astype(float)

    # ----- 量比（当日 / 过去5日均量）-----
    if len(df) >= 6:
        last_vol = vol.iloc[-1]
        avg5_prev = vol.iloc[-6:-1].mean()
        result["vol_ratio"] = float(last_vol / avg5_prev) if avg5_prev > 0 else None

    # ----- 均量线 MAVOL5/10/20 -----
    if len(df) >= 5:
        result["mavol5"] = float(vol.iloc[-5:].mean())
    if len(df) >= 10:
        result["mavol10"] = float(vol.iloc[-10:].mean())
    if len(df) >= 20:
        result["mavol20"] = float(vol.iloc[-20:].mean())

    # ----- 量价关系分类（当日价涨跌 × 量增缩）-----
    result["vol_price_trend"] = _classify_vol_price(df)

    # ----- OBV 能量潮 -----
    result["obv"], result["obv_signal"] = _calc_obv(df)

    # ----- VR 容量比率（默认 26 日）-----
    result["vr"] = _calc_vr(df, period=26)

    # ----- Z-Score（20 日）-----
    result["vol_zscore"] = _calc_vol_zscore(df)

    # ----- 放量突破 / 缩量回踩 -----
    result["breakout"] = _detect_breakout(df)
    result["pullback"] = _detect_pullback(df)

    return result


def _classify_vol_price(df: pd.DataFrame) -> str:
    """量价关系分类（设计 §3.1 量价同向）。
    价涨量增=同向多 / 价跌量增=同向空 / 价涨量缩=顶背离 /
    价跌量缩=底背离 / 其他=中性。"""
    if len(df) < 6:
        return "中性"
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    price_up = close.iloc[-1] > close.iloc[-2]
    price_dn = close.iloc[-1] < close.iloc[-2]
    avg5_prev = vol.iloc[-6:-1].mean()
    if avg5_prev == 0:
        return "中性"
    vol_up = vol.iloc[-1] > avg5_prev
    vol_dn = vol.iloc[-1] < avg5_prev

    if price_up and vol_up:
        return "同向多"
    if price_dn and vol_up:
        return "同向空"
    if price_up and vol_dn:
        return "顶背离"
    if price_dn and vol_dn:
        return "底背离"
    return "中性"


def _calc_obv(df: pd.DataFrame) -> tuple:
    """OBV 累积 + 信号判断。
    信号：当日 OBV 创近 60 日新高但收盘价未创同期新高 → '新高'；
          创新低且价未创新低 → '新低'；否则 '持平'。"""
    if len(df) < 2:
        return None, "持平"
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    direction = np.sign(close.diff().fillna(0))
    obv_series = (direction * vol).cumsum()
    last_obv = float(obv_series.iloc[-1])
    last_close = float(close.iloc[-1])

    window = min(60, len(df))
    obv_prev_max = float(obv_series.iloc[-window:-1].max())
    obv_prev_min = float(obv_series.iloc[-window:-1].min())
    close_prev_max = float(close.iloc[-window:-1].max())
    close_prev_min = float(close.iloc[-window:-1].min())

    signal = "持平"
    if last_obv > obv_prev_max and last_close <= close_prev_max:
        signal = "新高"   # 底部蓄势
    elif last_obv < obv_prev_min and last_close >= close_prev_min:
        signal = "新低"
    return last_obv, signal


def _calc_vr(df: pd.DataFrame, period: int = 26) -> Optional[float]:
    """VR 容量比率 = period 日内上涨日成交量之和 / 下跌日成交量之和 × 100。"""
    if len(df) < period + 1:
        return None
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    direction = np.sign(close.diff())
    up_vol = float((vol[direction > 0]).iloc[-(period - 1):].sum())
    dn_vol = float((vol[direction < 0]).iloc[-(period - 1):].sum())
    if dn_vol == 0:
        return None
    return up_vol / dn_vol * 100


def _calc_vol_zscore(df: pd.DataFrame, window: int = 20) -> Optional[float]:
    """成交量 Z-Score = (当日量 - window日均量) / window日标准差。"""
    if len(df) < window + 1:
        return None
    vol = df["volume"].astype(float)
    prev = vol.iloc[-(window + 1):-1]
    std = float(prev.std(ddof=0))
    if std == 0:
        return None
    return float((vol.iloc[-1] - prev.mean()) / std)


def _detect_breakout(df: pd.DataFrame) -> Optional[bool]:
    """放量突破：量比>2 且 close > 过去20日最高价（不含当日）。"""
    if len(df) < 21:
        return None
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    vol = df["volume"].astype(float)
    avg5_prev = vol.iloc[-6:-1].mean()
    if avg5_prev == 0:
        return False
    ratio = vol.iloc[-1] / avg5_prev
    prev_high_max = float(high.iloc[-21:-1].max())
    return bool(ratio > 2 and close.iloc[-1] > prev_high_max)


def _detect_pullback(df: pd.DataFrame) -> Optional[bool]:
    """缩量回踩：量比<0.7 且 close 在 MA10 或 MA20 的 ±1% 区间。"""
    if len(df) < 21:
        return None
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    avg5_prev = vol.iloc[-6:-1].mean()
    if avg5_prev == 0:
        return False
    ratio = vol.iloc[-1] / avg5_prev
    last_close = float(close.iloc[-1])
    ma10 = float(close.iloc[-10:].mean())
    ma20 = float(close.iloc[-20:].mean())
    def near(ma):
        return abs(last_close - ma) / ma <= 0.01
    return bool(ratio < 0.7 and (near(ma10) or near(ma20)))


# ============ 分时成交量聚合（§3.3） ============

# 4 个时段定义：(起始, 结束]，用于 hour_distribution
_TIME_SLOTS = [
    ("09:30", "10:30"),
    ("10:30", "11:30"),
    ("13:00", "14:00"),
    ("14:00", "15:00"),
]


def analyze_volume_minute(df: pd.DataFrame) -> dict:
    """分钟线维度的成交量聚合。

    输入: query_minute() 返回的 DataFrame（含 trade_time/volume/amount）
    输出: {
        'vwap','vwap_deviation',
        'hour_distribution': dict,  # 4 时段成交量占比
        'tail_concentration': float,
        'volume_peaks': list[dict],  # Top5：{'time','volume'}
    }
    """
    result = {
        "vwap": None, "vwap_deviation": None,
        "hour_distribution": {},
        "tail_concentration": None,
        "volume_peaks": [],
    }
    if df is None or df.empty:
        return result

    df = df.copy()
    df["trade_time"] = pd.to_datetime(df["trade_time"])
    vol = df["volume"].astype(float)
    amount = df["amount"].astype(float)

    # ----- VWAP -----
    total_v = float(vol.sum())
    if total_v > 0:
        vwap = float(amount.sum() / total_v)
        result["vwap"] = vwap
        last_close = float(df["close"].iloc[-1])
        if vwap > 0:
            result["vwap_deviation"] = (last_close - vwap) / vwap * 100

    # ----- 小时段分布 -----
    result["hour_distribution"] = _hour_distribution(df)

    # ----- 尾盘集中度（14:30-15:00）-----
    if total_v > 0:
        tail_mask = _slot_mask(df, "14:30", "15:00")
        result["tail_concentration"] = float(vol[tail_mask].sum() / total_v)

    # ----- 分时量峰 Top5 -----
    top = df.nlargest(5, "volume")[["trade_time", "volume"]]
    result["volume_peaks"] = [
        {"time": str(t), "volume": float(v)}
        for t, v in zip(top["trade_time"], top["volume"])
    ]
    return result


def _slot_mask(df: pd.DataFrame, start_hhmm: str, end_hhmm: str) -> pd.Series:
    """构造 [start, end) 时段布尔掩码（只比较时分）。"""
    t = df["trade_time"].dt.strftime("%H:%M")
    return (t >= start_hhmm) & (t < end_hhmm)


def _hour_distribution(df: pd.DataFrame) -> dict:
    """4 时段成交量占比（key 为 'HH:MM-HH:MM'）。"""
    vol = df["volume"].astype(float)
    total = float(vol.sum())
    if total == 0:
        return {}
    out = {}
    for s, e in _TIME_SLOTS:
        mask = _slot_mask(df, s, e)
        out[f"{s}-{e}"] = float(vol[mask].sum() / total)
    return out


# ============ 量能异动检测（§3.2） ============

def detect_volume_anomaly(df: pd.DataFrame,
                          minute_df: pd.DataFrame = None) -> dict:
    """量能异动检测。

    输入:
      df:        query_daily() 返回的 DataFrame（含 volume/turnover）
      minute_df: 可选，query_minute() 返回的 DataFrame；用于大单比例估算
    输出: {
        'vol_zscore': float,
        'turnover_spike': float,    # 换手率突增倍数
        'large_order_ratio': float, # 大单比例估算(minute_df 为 None 时为 None)
    }
    """
    result = {"vol_zscore": None, "turnover_spike": None, "large_order_ratio": None}
    if df is None or df.empty:
        return result

    df = df.reset_index(drop=True)
    # Z-Score（复用日线分析同口径）
    result["vol_zscore"] = _calc_vol_zscore(df)

    # 换手率突增 = 当日换手率 / 过去20日平均换手率
    if "turnover" in df.columns and len(df) >= 21:
        turn = df["turnover"].astype(float)
        avg20_prev = float(turn.iloc[-21:-1].mean())
        if avg20_prev > 0:
            result["turnover_spike"] = float(turn.iloc[-1] / avg20_prev)

    # 大单比例估算（需分钟数据）
    if minute_df is not None and not minute_df.empty and len(df) >= 6:
        result["large_order_ratio"] = _estimate_large_order_ratio(df, minute_df)

    return result


def _estimate_large_order_ratio(df: pd.DataFrame,
                                minute_df: pd.DataFrame) -> Optional[float]:
    """大单比例 = 分钟线中 volume > 当日均量×3 的根数占比。"""
    daily_vols = df["volume"].astype(float)
    avg5_prev = daily_vols.iloc[-6:-1].mean()
    threshold = avg5_prev * 3
    if threshold <= 0:
        return None
    mv = minute_df["volume"].astype(float)
    return float((mv > threshold).sum() / len(mv))
