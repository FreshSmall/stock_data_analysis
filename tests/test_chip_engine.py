"""
chip_engine 离线单测 — 本地 CYQ 算法正确性 + 筹码标签判定

不依赖网络/DB，构造合成 K 线验证：
  - 分布单调性（一字板、三角分布）
  - 获利比例 ∈ [0,1]
  - 集中度 ∈ [0,1)
  - 平均成本介于 90/70 区间内
  - chip_signal_label 四象限分类
"""
import json
import math
from datetime import date, timedelta

import pandas as pd
import pytest

import chip_engine
from chip_engine import (
    _calc_one_point, compute_chip_distribution, latest_chip_summary,
    chip_signal_label, RANGE, FACTOR,
)


# ---------- 测试夹具 ----------

def _make_kline(o, c, h, l, turnover=1.0, d=None):
    """构造单根 K 线 dict。"""
    return {"open": o, "close": c, "high": h, "low": l,
            "turnover": turnover, "trade_date": d or date.today()}


def _flat_df(days=130, price=10.0, turnover=1.0):
    """构造 N 天横盘 K 线 DataFrame（价格恒定）。"""
    rows = []
    base = date(2026, 1, 1)
    for i in range(days):
        rows.append({
            "trade_date": base + timedelta(days=i),
            "open": price, "close": price, "high": price, "low": price,
            "turnover": turnover,
        })
    return pd.DataFrame(rows)


def _rising_df(days=130, start=10.0, step=0.1, turnover=1.0):
    """构造单调上涨 K 线。"""
    rows = []
    base = date(2026, 1, 1)
    for i in range(days):
        p = start + i * step
        rows.append({
            "trade_date": base + timedelta(days=i),
            "open": p, "close": p + step / 2, "high": p + step, "low": p,
            "turnover": turnover,
        })
    return pd.DataFrame(rows)


# ---------- _calc_one_point 基础正确性 ----------

class TestCalcOnePoint:
    def test_empty_returns_none(self):
        assert _calc_one_point([], 0) is None

    def test_single_one_price_board(self):
        """单根一字板：所有筹码集中在单一价位。"""
        k = _make_kline(10, 10, 10, 10, turnover=5.0)
        r = _calc_one_point([k], 0)
        assert r is not None
        # _calc_one_point 返回 distribution 为 list（compute_chip_distribution 才转 JSON）
        dist = r["distribution"]
        assert isinstance(dist, list)
        assert len(dist) == 1
        # 单价 10，全部成本 = 10，获利比例 = 1（当前价 10 ≥ 自己）
        assert r["avg_cost"] == 10.0
        assert r["profit_ratio"] == pytest.approx(1.0, abs=1e-3)

    def test_profit_ratio_range(self):
        """获利比例恒在 [0, 1]。"""
        df = _rising_df(130)
        klines = df.to_dict("records")
        for i in (0, 50, 129):
            r = _calc_one_point(klines, i)
            assert 0 <= r["profit_ratio"] <= 1

    def test_concentration_range(self):
        """集中度 ∈ [0, 1)（同价位时趋近 0；发散时趋近 1）。"""
        df = _rising_df(130, step=0.5)
        r = _calc_one_point(df.to_dict("records"), 129)
        assert 0 <= r["concentration_90"] < 1
        assert 0 <= r["concentration_70"] < 1

    def test_concentration_70_le_90(self):
        """70% 区间应窄于 90% 区间（集中度 70 ≤ 90）。"""
        df = _rising_df(130, step=0.2)
        r = _calc_one_point(df.to_dict("records"), 129)
        assert r["concentration_70"] <= r["concentration_90"]

    def test_avg_cost_within_90_band(self):
        """平均成本应落在 90% 区间 [cost_90_low, cost_90_high] 之内。"""
        df = _rising_df(130, step=0.1)
        r = _calc_one_point(df.to_dict("records"), 129)
        assert r["cost_90_low"] <= r["avg_cost"] <= r["cost_90_high"]
        assert r["cost_70_low"] <= r["avg_cost"] <= r["cost_70_high"]

    def test_rising_trend_low_profit_ratio(self):
        """持续上涨末段，当前价远高于大部分筹码成本 → 获利比例接近 1。"""
        df = _rising_df(130, start=10, step=0.3)
        r = _calc_one_point(df.to_dict("records"), 129)
        # 价格从 10 涨到 ~49，绝大部分筹码都在下方
        assert r["profit_ratio"] > 0.9

    def test_distribution_sums_to_one(self):
        """distribution 权重归一化后总和 ≈ 1。"""
        df = _rising_df(130, step=0.1)
        r = _calc_one_point(df.to_dict("records"), 129)
        # _calc_one_point 返回 list
        dist = r["distribution"]
        total = sum(w for _, w in dist)
        assert total == pytest.approx(1.0, abs=0.02)


# ---------- compute_chip_distribution ----------

class TestComputeDistribution:
    def test_empty_df(self):
        assert compute_chip_distribution(pd.DataFrame()) == []

    def test_returns_requested_days(self):
        """last_n 参数控制返回天数。"""
        df = _rising_df(130, step=0.1)
        rows = compute_chip_distribution(df, last_n=10)
        assert len(rows) == 10
        # 每行都包含完整字段
        for r in rows:
            assert "trade_date" in r
            assert "profit_ratio" in r
            assert "distribution" in r  # JSON 字符串

    def test_distribution_is_json_string(self):
        df = _flat_df(130)
        rows = compute_chip_distribution(df, last_n=3)
        for r in rows:
            assert isinstance(r["distribution"], str)
            parsed = json.loads(r["distribution"])
            assert isinstance(parsed, list)

    def test_missing_column_raises(self):
        df = pd.DataFrame([{"open": 1, "close": 1, "high": 1, "low": 1}])  # 缺 turnover
        with pytest.raises(ValueError, match="缺少列"):
            compute_chip_distribution(df, last_n=1)


# ---------- latest_chip_summary ----------

class TestLatestChipSummary:
    def test_returns_last_day_without_distribution(self):
        df = _rising_df(130, step=0.1)
        r = latest_chip_summary(df)
        assert r is not None
        assert "distribution" not in r
        assert "profit_ratio" in r


# ---------- chip_signal_label 四象限 ----------

class TestChipSignalLabel:
    def test_locked(self):
        """低获利 + 高集中 → 筹码锁定。"""
        label, reason = chip_signal_label(0.2, 0.1, 10.0, 11.0)
        assert label == "筹码锁定"
        assert "获利盘" in reason and "集中度" in reason

    def test_converge(self):
        """中等获利 + 中等集中 → 筹码收敛。"""
        label, _ = chip_signal_label(0.4, 0.15, 10.0, 10.5)
        assert label == "筹码收敛"

    def test_heavy_profit(self):
        """高获利 → 获利盘堆积。"""
        label, reason = chip_signal_label(0.9, 0.3, 10.0, 12.0)
        assert label == "获利盘堆积"
        assert "压力" in reason

    def test_neutral(self):
        """其它 → 筹码分散。"""
        label, _ = chip_signal_label(0.6, 0.3, 10.0, 10.5)
        assert label == "筹码分散"

    def test_zero_price_returns_neutral(self):
        """close=0 时返回中性（避免除零）。"""
        label, _ = chip_signal_label(0.2, 0.1, 10.0, 0.0)
        assert label == "筹码分散"


# ---------- 常量一致性 ----------

class TestConstants:
    def test_constants_match_em(self):
        """与东方财富 CYQ 算法常量一致：120 天回看，150 价位桶。"""
        assert RANGE == 120
        assert FACTOR == 150
