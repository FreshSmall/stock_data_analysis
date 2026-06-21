"""
筹码分布引擎（chip / CYQ）

本地复现东方财富 "筹码分布" 算法（akshare stock_cyq_em 内嵌的 CYQCalculator.js），
不依赖 push2his.eastmoney.com（本机网络阻断），只用本地 daily_prices 数据计算。

核心算法（与东财完全一致）:
  1. 取当前价往前 range(=120) 个交易日的 K 线
  2. 在 [min(low), max(high)] 之间按 factor(=150) 个价位分桶
  3. 每根 K 线按当日 OHLC 均价为顶点的"三角分布"注入筹码
     注入量 = (该价位三角权重) × min(换手率, 1)
     之前所有筹码按 (1-换手率) 衰减（模拟获利盘卖出 / 新筹码换手）
  4. 由分布推导:
     - 获利比例 benefit_part: 当前价下方筹码 / 总筹码
     - 平均成本 avg_cost:     累计 50% 筹码对应的价位
     - 90/70 集中度:           取累计 (1-p)/2 与 (1+p)/2 筹码对应的两个价位 a,b
                              concentration = (b-a)/(b+a)  越小=筹码越集中

参考:
  akshare/stock_feature/stock_cyq_em.py 内嵌的 CYQCalculator / CYQData / getCostByChip
  https://quote.eastmoney.com/concept/sz000001.html (筹码分布图)
"""
from __future__ import annotations

import json
import math
from typing import Optional

import pandas as pd


# —— 算法常量（与东财 JS 完全一致）——
RANGE = 120      # 回看交易日数
FACTOR = 150     # 价位桶数


def _calc_one_point(klines: list[dict], index: int) -> Optional[dict]:
    """对单根 K 线（index）计算筹码分布及衍生指标。

    klines: 按 trade_date 升序的 K 线列表，元素含 open/close/high/low/turnover
    返回 dict（无数据返回 None）:
      profit_ratio, avg_cost, cost_90_low/high, concentration_90,
      cost_70_low/high, concentration_70, distribution
    """
    start = max(0, index - RANGE + 1)
    kdata = klines[start:index + 1]
    if not kdata:
        return None

    # —— 1. 价格区间与桶宽 ——
    highs = [k["high"] for k in kdata]
    lows = [k["low"] for k in kdata]
    maxprice = max(highs)
    minprice = min(lows)
    if maxprice <= minprice:
        # 一字板/数据异常，价位宽度 0
        accuracy = 0.01
    else:
        accuracy = max(0.01, (maxprice - minprice) / (FACTOR - 1))

    # 价位数组 yrange[i] = minprice + i*accuracy
    # —— 2. 累积分布 xdata[i] ——
    xdata = [0.0] * FACTOR
    for k in kdata:
        o, c, h, l = k["open"], k["close"], k["high"], k["low"]
        avg = (o + c + h + l) / 4
        turnover_rate = min(1.0, (k.get("turnover") or 0) / 100.0)

        # 衰减：原有筹码按 (1-换手率) 衰减
        for n in range(FACTOR):
            xdata[n] *= (1 - turnover_rate)

        if h == l:
            # 一字板：矩形面积 = 三角形 2 倍
            gi = int((avg - minprice) // accuracy)
            gi = max(0, min(FACTOR - 1, gi))
            xdata[gi] += (FACTOR - 1) * turnover_rate / 2
        else:
            # 三角分布：[low, avg] 上行，[avg, high] 下行
            H = int((h - minprice) // accuracy)
            L = math.ceil((l - minprice) / accuracy)
            L = max(0, L)
            H = min(FACTOR - 1, H)
            g_weight = 2 / (h - l)
            for j in range(L, H + 1):
                curprice = minprice + accuracy * j
                if curprice <= avg:
                    if abs(avg - l) < 1e-8:
                        add = g_weight * turnover_rate
                    else:
                        add = (curprice - l) / (avg - l) * g_weight * turnover_rate
                else:
                    if abs(h - avg) < 1e-8:
                        add = g_weight * turnover_rate
                    else:
                        add = (h - curprice) / (h - avg) * g_weight * turnover_rate
                xdata[j] += add

    total = sum(xdata)
    if total <= 0:
        return None

    # —— 3. 衍生指标 ——
    current_price = klines[index]["close"]

    def get_cost_by_chip(chip: float) -> float:
        """累计到 chip 筹码量对应的价位（中点查找）。"""
        s = 0.0
        for i in range(FACTOR):
            s += xdata[i]
            if s > chip:
                return minprice + i * accuracy
        return minprice + (FACTOR - 1) * accuracy

    def get_benefit_part(price: float) -> float:
        """价格下方筹码占比（获利盘比例）。"""
        below = 0.0
        for i in range(FACTOR):
            if price >= minprice + i * accuracy:
                below += xdata[i]
        return below / total

    def compute_percent_chips(p: float) -> tuple[float, float, float]:
        """返回 (price_low, price_high, concentration)。"""
        ps = ((1 - p) / 2, (1 + p) / 2)
        pl = get_cost_by_chip(total * ps[0])
        ph = get_cost_by_chip(total * ps[1])
        conc = 0.0 if (pl + ph) == 0 else (ph - pl) / (pl + ph)
        return pl, ph, conc

    avg_cost = get_cost_by_chip(total * 0.5)
    profit_ratio = get_benefit_part(current_price)
    c90_low, c90_high, conc90 = compute_percent_chips(0.9)
    c70_low, c70_high, conc70 = compute_percent_chips(0.7)

    # 筹码分布序列（稀疏化：过滤权重过小的桶）
    dist = [
        [round(minprice + i * accuracy, 2), round(x / total, 6)]
        for i, x in enumerate(xdata) if x > 0
    ]

    return {
        "profit_ratio": round(profit_ratio, 6),
        "avg_cost": round(avg_cost, 3),
        "cost_90_low": round(c90_low, 3),
        "cost_90_high": round(c90_high, 3),
        "concentration_90": round(conc90, 4),
        "cost_70_low": round(c70_low, 3),
        "cost_70_high": round(c70_high, 3),
        "concentration_70": round(conc70, 4),
        "distribution": dist,
    }


def compute_chip_distribution(daily_df: pd.DataFrame,
                              last_n: int = 90) -> list[dict]:
    """对日线 DataFrame 计算最近 last_n 个交易日的筹码分布。

    daily_df: 至少含 trade_date/open/close/high/low/turnover，按 trade_date 升序更佳
              （内部会 sort_values 保证升序）
    last_n:   只计算最后 N 天（默认 90，与东财接口一致）

    返回 list[dict]，每条含 trade_date + chip 指标（无数据的日期被跳过）。
    """
    if daily_df is None or daily_df.empty:
        return []

    # 先校验列齐全（包含 trade_date + 量价 + turnover）
    required = ["trade_date", "open", "close", "high", "low", "turnover"]
    missing = [c for c in required if c not in daily_df.columns]
    if missing:
        raise ValueError(f"daily_df 缺少列: {missing}")

    df = daily_df.sort_values("trade_date").reset_index(drop=True)
    # 仅取最近 RANGE + last_n 行保证指标稳定（计算某天时需要前 120 天）
    need = RANGE + last_n
    if len(df) > need:
        df = df.iloc[-need:].reset_index(drop=True)

    klines = []
    for _, row in df.iterrows():
        klines.append({
            "trade_date": row["trade_date"],
            "open": float(row["open"]), "close": float(row["close"]),
            "high": float(row["high"]), "low": float(row["low"]),
            "turnover": float(row["turnover"]) if pd.notna(row["turnover"]) else 0.0,
        })

    results = []
    # 从能完整计算的索引（>=0）开始，取最后 last_n 个
    start_idx = max(0, len(klines) - last_n)
    for i in range(start_idx, len(klines)):
        chip = _calc_one_point(klines, i)
        if chip is None:
            continue
        chip["trade_date"] = klines[i]["trade_date"]
        chip["distribution"] = json.dumps(chip["distribution"], ensure_ascii=False)
        results.append(chip)
    return results


def latest_chip_summary(daily_df: pd.DataFrame) -> Optional[dict]:
    """便捷：只返回最新一天的筹码摘要（不含 distribution）。"""
    rows = compute_chip_distribution(daily_df, last_n=1)
    if not rows:
        return None
    r = dict(rows[-1])
    r.pop("distribution", None)
    return r


def chip_signal_label(profit_ratio: float, concentration: float,
                      avg_cost: float, close: float) -> tuple[str, str]:
    """根据筹码指标输出短线标签与提示文本（用于信号评分 / 前端展示）。

    逻辑:
      - 获利比例 < 0.30 且 集中度 < 0.15: 「筹码锁定」上方套牢盘少+集中度高 → 推荐关注
      - 获利比例 < 0.50 且 集中度 < 0.20: 「筹码收敛」套牢压力小
      - 获利比例 > 0.85:                  「获利盘堆积」接近顶部压力区
      - 其它:                              「筹码分散」

    返回 (label, reason)
    """
    if close <= 0 or avg_cost <= 0:
        return "筹码分散", ""
    cost_dev = (close - avg_cost) / avg_cost  # 收盘价相对平均成本偏离

    if profit_ratio < 0.30 and concentration < 0.15:
        return ("筹码锁定", f"获利盘仅{profit_ratio*100:.0f}%、集中度{concentration*100:.1f}%，"
                f"套牢压力小、筹码集中，价格在均成本{cost_dev*100:+.1f}%")
    if profit_ratio < 0.50 and concentration < 0.20:
        return ("筹码收敛", f"获利盘{profit_ratio*100:.0f}%、集中度{concentration*100:.1f}%，"
                f"上方压力较轻")
    if profit_ratio > 0.85:
        return ("获利盘堆积", f"获利盘高达{profit_ratio*100:.0f}%，接近压力区，"
                f"价格高于均成本{cost_dev*100:+.1f}%")
    return ("筹码分散", f"获利盘{profit_ratio*100:.0f}%、集中度{concentration*100:.1f}%，"
            f"无明显方向")
