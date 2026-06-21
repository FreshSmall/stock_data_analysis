"""
signal_scorer 离线单测 — 5 维计分(§8.1-§8.5) + 标签映射(§8.6)
全部用构造的 ind dict 断言区间边界，无 DB/网络。
"""
import pytest

from core.scoring.signal_scorer import (
    _score_vol_price,
    _score_trend,
    _score_momentum,
    _score_anomaly,
    _score_intraday,
    map_label,
    build_reason,
)


# ============ §8.1 量价配合（满分30） ============

class TestScoreVolPrice:
    """量价同向10 / 量比8 / MAVOL5v10 6 / 放量突破4 / 缩量回踩2"""

    def test_vol_price_same_up(self):
        assert _score_vol_price({"vol_price_trend": "同向多"}) >= 0  # 子项内含

    def test_vol_price_subitem_same_up(self):
        """同向多 → 10（其他项用 None 表示无贡献）"""
        ind = {"vol_price_trend": "同向多", "vol_ratio": None,
               "mavol5": None, "mavol10": None, "breakout": False, "pullback": False}
        assert _score_vol_price(ind) == 10

    def test_vol_price_same_down(self):
        """同向空 → 7"""
        ind = {"vol_price_trend": "同向空", "vol_ratio": None,
               "mavol5": None, "mavol10": None, "breakout": False, "pullback": False}
        assert _score_vol_price(ind) == 7

    def test_vol_price_divergence(self):
        """顶背离/底背离 → 3"""
        for trend in ("顶背离", "底背离"):
            ind = {"vol_price_trend": trend, "vol_ratio": None,
                   "mavol5": None, "mavol10": None, "breakout": False, "pullback": False}
            assert _score_vol_price(ind) == 3

    def test_vol_price_neutral(self):
        """中性 → 0"""
        ind = {"vol_price_trend": "中性", "vol_ratio": None,
               "mavol5": None, "mavol10": None, "breakout": False, "pullback": False}
        assert _score_vol_price(ind) == 0

    @pytest.mark.parametrize("ratio,expected", [
        (2.5, 8), (1.5, 6), (1.5 - 1e-9, 4),  # 1.5 边界归 6
        (1.0, 4), (1.0 - 1e-9, 3),             # 1.0 边界归 4
        (0.5, 3), (0.5 - 1e-9, 2),             # 0.5 边界归 3
        (0.3, 2),
    ])
    def test_vol_ratio_buckets(self, ratio, expected):
        ind = {"vol_price_trend": "中性", "vol_ratio": ratio,
               "mavol5": None, "mavol10": None, "breakout": False, "pullback": False}
        # 只看量比贡献 = expected（中性+0+0+0+0 = expected）
        assert _score_vol_price(ind) == expected

    def test_mavol5_cross_above(self):
        """MAVOL5 上穿 MAVOL10 → 6"""
        ind = {"vol_price_trend": "中性", "vol_ratio": None,
               "mavol5": 100, "mavol10": 90, "mavol5_prev": 85, "mavol10_prev": 95,
               "breakout": False, "pullback": False}
        # 金叉检测：mavol5>mavol10 且 prev 反向
        assert _score_vol_price(ind) == 6

    def test_mavol5_above(self):
        """MAVOL5>MAVOL10（非金叉）→ 4"""
        ind = {"vol_price_trend": "中性", "vol_ratio": None,
               "mavol5": 100, "mavol10": 90, "mavol5_prev": 95, "mavol10_prev": 85,
               "breakout": False, "pullback": False}
        assert _score_vol_price(ind) == 4

    def test_mavol5_below(self):
        """MAVOL5<MAVOL10 → 2"""
        ind = {"vol_price_trend": "中性", "vol_ratio": None,
               "mavol5": 80, "mavol10": 90, "mavol5_prev": 75, "mavol10_prev": 95,
               "breakout": False, "pullback": False}
        assert _score_vol_price(ind) == 2

    def test_breakout_adds_4(self):
        ind = {"vol_price_trend": "中性", "vol_ratio": None,
               "mavol5": None, "mavol10": None, "breakout": True, "pullback": False}
        assert _score_vol_price(ind) == 4

    def test_pullback_adds_2(self):
        ind = {"vol_price_trend": "中性", "vol_ratio": None,
               "mavol5": None, "mavol10": None, "breakout": False, "pullback": True}
        assert _score_vol_price(ind) == 2

    def test_full_score_30(self):
        """满分 30：同向多(10) + 量比2.5(8) + MAVOL金叉(6) + 放量突破(4) + 缩量回踩(2)"""
        ind = {"vol_price_trend": "同向多", "vol_ratio": 2.5,
               "mavol5": 100, "mavol10": 90, "mavol5_prev": 85, "mavol10_prev": 95,
               "breakout": True, "pullback": True}
        assert _score_vol_price(ind) == 30


# ============ §8.2 趋势方向（满分25） ============

class TestScoreTrend:
    """MA排列10 / MA5斜率5 / MACD柱5 / 乖离5"""

    def test_ma_full_bull_alignment(self):
        """多头排列 MA5>MA10>MA20>MA60 → 10"""
        ind = {"ma5": 11, "ma10": 10.5, "ma20": 10, "ma60": 9.5,
               "ma5_prev": 10.8, "close": 11.2,
               "macd_hist": 0.3, "macd_hist_prev": 0.2}
        score = _score_trend(ind)
        assert 18 <= score <= 25  # 排列10 + 斜率上扬 + 红柱放大 + 乖离正常

    def test_ma_alignment_only(self):
        """仅多头排列 → 10（其他项取 0/中性）"""
        ind = {"ma5": 11, "ma10": 10.5, "ma20": 10, "ma60": 9.5,
               "ma5_prev": 11, "close": 11,
               "macd_hist": 0, "macd_hist_prev": 0}
        # close==ma20? 乖离按 close>ma20 判断
        assert _score_trend(ind) >= 10

    def test_ma_bear_alignment(self):
        """空头排列 → 0（MA 排列分）"""
        ind = {"ma5": 9, "ma10": 9.5, "ma20": 10, "ma60": 10.5,
               "ma5_prev": 9, "close": 8.5,
               "macd_hist": -0.3, "macd_hist_prev": -0.2}
        score = _score_trend(ind)
        assert score < 10  # 排列 0，其余也很低

    def test_ma5_slope_up_strong(self):
        """MA5 上扬 > 1% → 5"""
        # close>ma20，乖离小；只测斜率子项 → 用排列缠绕控制其他
        ind = {"ma5": 10.2, "ma10": 10.2, "ma20": 10.2, "ma60": 10.2,  # 缠绕
               "ma5_prev": 10.0, "close": 10.25,
               "macd_hist": 0, "macd_hist_prev": 0}
        # 缠绕(3) + 斜率(5，上扬2%) + 乖离(5，close>ma20 偏离<10%)
        assert _score_trend(ind) == 3 + 5 + 5

    def test_ma5_slope_flat(self):
        """MA5 走平 → 2"""
        ind = {"ma5": 10.0, "ma10": 10.0, "ma20": 10.0, "ma60": 10.0,
               "ma5_prev": 10.0, "close": 10.0,
               "macd_hist": 0, "macd_hist_prev": 0}
        # 缠绕(3) + 走平(2) + macd持平(看实现) + 乖离(close<ma20→2 或 =0)
        score = _score_trend(ind)
        assert 3 <= score <= 10

    def test_macd_red_bar_expanding(self):
        """MACD 红柱放大 → 5"""
        ind = {"ma5": 10, "ma10": 10, "ma20": 10, "ma60": 10,
               "ma5_prev": 10, "close": 10,
               "macd_hist": 0.5, "macd_hist_prev": 0.3}
        # 持平部分 + macd放大(5)
        base = _score_trend({"ma5": 10, "ma10": 10, "ma20": 10, "ma60": 10,
                             "ma5_prev": 10, "close": 10,
                             "macd_hist": 0, "macd_hist_prev": 0})
        assert _score_trend(ind) == base + 5

    def test_deviation_high(self):
        """乖离 > 20% → 1"""
        ind = {"ma5": 10, "ma10": 10, "ma20": 10, "ma60": 10,
               "ma5_prev": 10, "close": 13,  # 偏离 30%
               "macd_hist": 0, "macd_hist_prev": 0}
        # 缠绕(3) + 走平(2) + macd(0) + 乖离(1)
        assert _score_trend(ind) == 3 + 2 + 0 + 1


# ============ §8.3 动量信号（满分20） ============

class TestScoreMomentum:
    """RSI 8 / MACD金叉6 / MA金叉4 / VR 2"""

    @pytest.mark.parametrize("rsi,expected", [
        (50, 8),   # 40-60 健康
        (35, 6),   # 30-40
        (65, 5),   # 60-70
        (25, 4),   # <30 超卖反弹预期
        (75, 2),   # >70 超买
    ])
    def test_rsi_buckets(self, rsi, expected):
        ind = {"rsi": rsi, "macd_golden": False, "macd_above": False,
               "ma_golden": False, "vr": 100}
        # 只测 RSI 贡献（其余 0/中性）
        assert _score_momentum(ind) == expected + 0 + 0 + 2  # vr=100 健康 → +2

    def test_macd_golden_today(self):
        """当日 MACD 金叉 → 6"""
        ind = {"rsi": 50, "macd_golden": True, "macd_above": True,
               "ma_golden": False, "vr": 100}
        assert _score_momentum(ind) == 8 + 6 + 0 + 2

    def test_macd_above_recent(self):
        """DIF>DEA 近 5 日内金叉 → 4"""
        ind = {"rsi": 50, "macd_golden": False, "macd_above": True,
               "macd_above_days": 3, "ma_golden": False, "vr": 100}
        assert _score_momentum(ind) == 8 + 4 + 0 + 2

    def test_macd_above_only(self):
        """DIF>DEA（>5日）→ 2"""
        ind = {"rsi": 50, "macd_golden": False, "macd_above": True,
               "macd_above_days": 10, "ma_golden": False, "vr": 100}
        assert _score_momentum(ind) == 8 + 2 + 0 + 2

    def test_ma_golden_today(self):
        """当日 MA 金叉 → 4"""
        ind = {"rsi": 50, "macd_golden": False, "macd_above": False,
               "ma_golden": True, "vr": 100}
        assert _score_momentum(ind) == 8 + 0 + 4 + 2

    @pytest.mark.parametrize("vr,expected", [
        (100, 2),   # 80-160 健康
        (30, 1),    # <40 过冷
        (250, 0),   # >200 过热
    ])
    def test_vr_buckets(self, vr, expected):
        ind = {"rsi": 50, "macd_golden": False, "macd_above": False,
               "ma_golden": False, "vr": vr}
        assert _score_momentum(ind) == 8 + 0 + 0 + expected

    def test_full_score_20(self):
        ind = {"rsi": 50, "macd_golden": True, "macd_above": True,
               "ma_golden": True, "vr": 100}
        assert _score_momentum(ind) == 20


# ============ §8.4 异动检测（满分15） ============

class TestScoreAnomaly:
    """Z-Score 6 / 换手率突增5 / 尾盘集中度4"""

    @pytest.mark.parametrize("z,expected", [
        (3.5, 6),   # |Z|>3
        (2.5, 4),   # 2<|Z|<=3
        (-2.5, 4),  # 负向同样
        (1.5, 2),   # 1<|Z|<=2
        (0.5, 1),   # <=1
    ])
    def test_zscore_buckets(self, z, expected):
        ind = {"vol_zscore": z, "turnover_spike": 1.0, "tail_concentration": 25}
        assert _score_anomaly(ind) == expected + 1 + 4  # spike<=1.5→1, tail 25-35→4

    @pytest.mark.parametrize("spike,expected", [
        (4.0, 5),   # >3
        (2.5, 4),   # 2-3
        (1.8, 2),   # 1.5-2
        (1.2, 1),   # <=1.5
    ])
    def test_turnover_spike_buckets(self, spike, expected):
        ind = {"vol_zscore": 0.5, "turnover_spike": spike, "tail_concentration": 25}
        assert _score_anomaly(ind) == 1 + expected + 4

    @pytest.mark.parametrize("tail,expected", [
        (30, 4),    # 25-35 正常偏高
        (40, 3),    # >35 异常
        (15, 2),    # <20
        (22, 1),    # 其余
    ])
    def test_tail_concentration_buckets(self, tail, expected):
        ind = {"vol_zscore": 0.5, "turnover_spike": 1.2, "tail_concentration": tail}
        assert _score_anomaly(ind) == 1 + 1 + expected


# ============ §8.5 分时确认（满分10） ============

class TestScoreIntraday:
    """VWAP偏离4 / 小时段分布4 / 分时连续性2"""

    @pytest.mark.parametrize("dev,close_above,expected", [
        (1.0, True, 4),    # 收盘>VWAP 偏离<2%
        (3.0, True, 3),    # 偏离 2-4%
        (5.0, True, 1),    # 偏离>4%
        (-1.0, False, 2),  # 收盘<VWAP
    ])
    def test_vwap_deviation_buckets(self, dev, close_above, expected):
        ind = {"vwap_deviation": dev, "close_above_vwap": close_above,
               "hour_pattern": "午后放量", "intraday_continuity": "稳定"}
        # pattern 午后放量→3, continuity 稳定→1
        assert _score_intraday(ind) == expected + 3 + 1

    @pytest.mark.parametrize("pattern,expected", [
        ("早盘+午后双峰", 4),
        ("午后放量", 3),
        ("早盘脉冲", 2),
        ("均匀", 2),
        ("尾盘异常", 1),
    ])
    def test_hour_pattern_buckets(self, pattern, expected):
        ind = {"vwap_deviation": 1.0, "close_above_vwap": True,
               "hour_pattern": pattern, "intraday_continuity": "稳定"}
        assert _score_intraday(ind) == 4 + expected + 1

    @pytest.mark.parametrize("cont,expected", [
        ("逐步放大", 2),
        ("稳定", 1),
        ("脉冲后萎缩", 0),
    ])
    def test_continuity_buckets(self, cont, expected):
        ind = {"vwap_deviation": 1.0, "close_above_vwap": True,
               "hour_pattern": "午后放量", "intraday_continuity": cont}
        assert _score_intraday(ind) == 4 + 3 + expected


# ============ §8.6 标签映射 ============

class TestMapLabel:
    @pytest.mark.parametrize("score,label", [
        (100, "强烈关注"),
        (80, "强烈关注"),
        (79, "值得关注"),
        (65, "值得关注"),
        (64, "中性观察"),
        (50, "中性观察"),
        (49, "暂不参与"),
        (0, "暂不参与"),
    ])
    def test_label_boundaries(self, score, label):
        assert map_label(score)[0] == label

    def test_returns_action(self):
        label, action = map_label(85)
        assert label == "强烈关注"
        assert action == "关注"

    def test_out_of_range_clamped(self):
        # < 0 当 0，> 100 当 100
        assert map_label(-5)[0] == "暂不参与"
        assert map_label(150)[0] == "强烈关注"


# ============ build_reason ============

class TestBuildReason:
    def test_returns_nonempty_string(self):
        scores = {"vol_price": 28, "trend": 20, "momentum": 15,
                  "anomaly": 10, "intraday": 8}
        ind = {"vol_ratio": 2.1, "breakout": True, "vol_price_trend": "同向多",
               "rsi": 55, "macd_golden": True, "limit_up": False}
        reason = build_reason(scores, ind)
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_includes_high_score_factors(self):
        """高分项应出现在理由中"""
        scores = {"vol_price": 28, "trend": 20, "momentum": 15,
                  "anomaly": 10, "intraday": 8}
        ind = {"vol_ratio": 2.1, "breakout": True, "vol_price_trend": "同向多",
               "rsi": 55, "macd_golden": True, "limit_up": False}
        reason = build_reason(scores, ind)
        assert "放量" in reason or "突破" in reason or "量比" in reason

    def test_limit_up_warning(self):
        """涨停时应追加风险提示"""
        scores = {"vol_price": 28, "trend": 20, "momentum": 15,
                  "anomaly": 10, "intraday": 8}
        ind = {"vol_ratio": 2.1, "breakout": True, "vol_price_trend": "同向多",
               "rsi": 55, "macd_golden": True, "limit_up": True}
        reason = build_reason(scores, ind)
        assert "涨停" in reason or "风险" in reason
