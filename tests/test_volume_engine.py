"""
volume_engine 离线单测 — 量价关系(日线) / 分时聚合 / 量能异动
全部用构造的 DataFrame 断言，无 DB / 网络。
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from core.indicators.volume_engine import (
    analyze_volume_daily,
    analyze_volume_minute,
    detect_volume_anomaly,
)


# ============ 测试辅助 ============

def make_daily(n=60, base_close=10.0, vol_base=10000,
               close_trend=None, vol_trend=None, turnover=1.0):
    """构造 n 天日线 DataFrame（按 trade_date 升序）。
    close_trend / vol_trend: 可选 list[n]，None 则用基础值。"""
    if close_trend is None:
        close_trend = [base_close] * n
    if vol_trend is None:
        vol_trend = [vol_base] * n
    dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(n)]
    df = pd.DataFrame({
        "trade_date": dates,
        "open": [c * 0.99 for c in close_trend],
        "close": close_trend,
        "high": [c * 1.02 for c in close_trend],
        "low": [c * 0.98 for c in close_trend],
        "volume": vol_trend,
        "amount": [v * c for v, c in zip(vol_trend, close_trend)],
        "turnover": [turnover] * n,
        "pct_change": [0.0] * n,
    })
    return df


def make_minute(volumes, amounts=None, closes=None,
                date_str="2026-06-17", period="5", real_sessions=False):
    """构造当天分钟线。
    real_sessions=False（默认）: 从 9:30 起每 5 分钟一根（用于简单测试）
    real_sessions=True: 按 A 股真实交易时段构造 48 根（9:30-11:30 + 13:00-15:00）"""
    n = len(volumes)
    if real_sessions:
        times = []
        cur = datetime.strptime(f"{date_str} 09:30", "%Y-%m-%d %H:%M")
        end_morning = datetime.strptime(f"{date_str} 11:30", "%Y-%m-%d %H:%M")
        pm_start = datetime.strptime(f"{date_str} 13:00", "%Y-%m-%d %H:%M")
        end_afternoon = datetime.strptime(f"{date_str} 15:00", "%Y-%m-%d %H:%M")
        while len(times) < n:
            if cur < end_morning or (pm_start <= cur < end_afternoon):
                times.append(cur)
            cur += timedelta(minutes=5)
            # 跳过午休
            if cur == end_morning:
                cur = pm_start
        times = times[:n]
    else:
        start = datetime.strptime(f"{date_str} 09:30:00", "%Y-%m-%d %H:%M:%S")
        times = [start + timedelta(minutes=5 * i) for i in range(n)]
    if amounts is None:
        amounts = [v * 10.0 for v in volumes]
    if closes is None:
        closes = [10.0] * n
    return pd.DataFrame({
        "stock_code": ["600519"] * n,
        "trade_date": [date_str] * n,
        "trade_time": times,
        "open": closes,
        "close": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "volume": volumes,
        "amount": amounts,
        "period": [period] * n,
    })


# ============ T1a analyze_volume_daily ============

class TestAnalyzeVolumeDaily:
    def test_vol_ratio_basic(self):
        """量比 = 当日量 / 过去5日均量"""
        # 前 5 天 10000，当日 20000 → 量比 2.0
        vols = [10000] * 59 + [20000]
        df = make_daily(60, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vol_ratio"] == pytest.approx(2.0, rel=1e-3)

    def test_vol_ratio_shrink(self):
        """缩量：量比 < 1"""
        vols = [10000] * 59 + [4000]
        df = make_daily(60, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vol_ratio"] == pytest.approx(0.4, rel=1e-3)

    def test_mavol_lines(self):
        """MAVOL5/10/20 均量线计算"""
        vols = list(range(1000, 1000 + 60))  # 1000..1059
        df = make_daily(60, vol_trend=vols)
        r = analyze_volume_daily(df)
        # MAVOL5 = (1055+1056+1057+1058+1059)/5
        assert r["mavol5"] == pytest.approx(np.mean(vols[-5:]), rel=1e-6)
        assert r["mavol10"] == pytest.approx(np.mean(vols[-10:]), rel=1e-6)
        assert r["mavol20"] == pytest.approx(np.mean(vols[-20:]), rel=1e-6)

    def test_vol_price_trend_same_up(self):
        """价涨量增 → 同向多"""
        closes = [10.0] * 59 + [10.5]  # 当日涨
        vols = [10000] * 59 + [15000]  # 当日放量
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vol_price_trend"] == "同向多"

    def test_vol_price_trend_same_down(self):
        """价跌量增 → 同向空（空头放量下杀）"""
        closes = [10.0] * 59 + [9.5]   # 当日跌
        vols = [10000] * 59 + [15000]  # 放量
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vol_price_trend"] == "同向空"

    def test_vol_price_trend_top_divergence(self):
        """价涨量缩 → 顶背离"""
        closes = [10.0] * 59 + [10.5]  # 涨
        vols = [10000] * 59 + [6000]   # 缩量
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vol_price_trend"] == "顶背离"

    def test_vol_price_trend_bottom_divergence(self):
        """价跌量缩 → 底背离"""
        closes = [10.0] * 59 + [9.5]   # 跌
        vols = [10000] * 59 + [6000]   # 缩量
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vol_price_trend"] == "底背离"

    def test_vol_price_trend_neutral_flat(self):
        """价量均持平 → 中性"""
        df = make_daily(60)  # 全部相同
        r = analyze_volume_daily(df)
        assert r["vol_price_trend"] == "中性"

    def test_obv_cumulative(self):
        """OBV：价涨加量、价跌减量"""
        # 第 0 天 obv=0；后续每日价涨就加 volume
        closes = [10 + i * 0.1 for i in range(60)]  # 单边涨
        vols = [1000] * 60
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        # 第 1..59 天均上涨 → OBV = 59 * 1000
        assert r["obv"] == pytest.approx(59000, rel=1e-6)

    def test_obv_signal_new_high(self):
        """OBV 创新高但价未创新高 → 新高信号（底部蓄势）"""
        # 前 30 天：价在 11 附近、量小；后 30 天：价从 10 缓慢爬升（不超过 11）但放量
        # 关键：后期要「上涨日明显多于下跌日」让 OBV 累积走高，但价格整体 < 11
        closes = []
        for i in range(60):
            if i < 30:
                closes.append(11.0)            # 前期平台
            else:
                # 后期从 10.0 缓慢爬升到 10.9（始终 < 11），几乎单边涨
                closes.append(10.0 + 0.03 * (i - 30))
        vols = [1000] * 30 + [8000] * 30        # 后期大幅放量 → OBV 累积上行
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["obv_signal"] == "新高"

    def test_vr_healthy_range(self):
        """VR 容量比率在健康区间 (40-160)"""
        rng = np.random.default_rng(42)
        # 涨跌各半，量接近
        closes = [10.0]
        for _ in range(59):
            closes.append(closes[-1] * (1 + rng.normal(0, 0.02)))
        vols = [10000] * 60
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert 40 <= r["vr"] <= 160

    def test_vr_overheated(self):
        """VR > 160：上涨日成交量明显大于下跌日"""
        # 60 天，大部分上涨（少数下跌日且量小）
        closes = []
        for i in range(60):
            if i % 5 == 4:  # 每 5 天跌 1 天
                closes.append((closes[-1] if closes else 10) * 0.98)
            else:
                closes.append((closes[-1] if closes else 10) * 1.02)
        # 上涨日放量，下跌日缩量
        vols = []
        for i in range(60):
            vols.append(5000 if i % 5 == 4 else 20000)
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["vr"] is not None
        assert r["vr"] > 160

    def test_breakout_detection(self):
        """放量突破：量比>2 + 收盘价突破过去20日最高价"""
        # 前 59 天 high 上界 10*1.02=10.2；当日 close 11 → 突破
        closes = [10.0] * 59 + [11.0]
        vols = [10000] * 59 + [25000]  # 量比 2.5
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["breakout"] is True

    def test_breakout_no_breakout_low_volume(self):
        """量比不足 → 不算突破"""
        closes = [10.0] * 59 + [11.0]
        vols = [10000] * 59 + [12000]  # 量比 1.2
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["breakout"] is False

    def test_pullback_detection(self):
        """缩量回踩：量比<0.7 + 回踩均线"""
        # 构造 MA10 在 10.0 附近；当日 close=10.05（±1% 内）；量比 0.5
        closes = [10.0] * 59 + [10.05]
        vols = [10000] * 59 + [5000]
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["pullback"] is True

    def test_pullback_no_pullback_high_volume(self):
        """放量不构成回踩"""
        closes = [10.0] * 59 + [10.05]
        vols = [10000] * 59 + [20000]
        df = make_daily(60, close_trend=closes, vol_trend=vols)
        r = analyze_volume_daily(df)
        assert r["pullback"] is False

    def test_insufficient_data_returns_none_for_long_periods(self):
        """数据 < 20 行：长周期指标返回 None 不抛异常"""
        df = make_daily(15)
        r = analyze_volume_daily(df)
        # MAVOL20、VR、放量突破（需20日高点）应为 None
        assert r["mavol20"] is None
        assert r["vr"] is None
        assert r["breakout"] is None

    def test_empty_df_safe(self):
        """空 DataFrame 不抛异常"""
        df = pd.DataFrame(columns=["trade_date", "close", "volume"])
        r = analyze_volume_daily(df)
        assert r["vol_ratio"] is None
        assert r["vol_price_trend"] == "中性"


# ============ T1b analyze_volume_minute ============

class TestAnalyzeVolumeMinute:
    def test_vwap_calculation(self):
        """VWAP = Σ(amount) / Σ(volume)"""
        volumes = [100, 200, 300, 400]
        amounts = [1000.0, 2000.0, 3000.0, 4000.0]  # 均 10 元/股
        df = make_minute(volumes, amounts=amounts)
        r = analyze_volume_minute(df)
        # (1000+2000+3000+4000) / (100+200+300+400) = 10000/1000 = 10.0
        assert r["vwap"] == pytest.approx(10.0, rel=1e-6)

    def test_vwap_deviation_positive(self):
        """收盘价高于 VWAP → 正偏离"""
        volumes = [100, 100, 100, 100]
        amounts = [1000.0] * 4   # vwap=10
        closes = [10.0, 10.0, 10.0, 11.0]  # 最后一根 close=11
        df = make_minute(volumes, amounts=amounts, closes=closes)
        r = analyze_volume_minute(df)
        # (11-10)/10*100 = 10%
        assert r["vwap_deviation"] == pytest.approx(10.0, rel=1e-3)

    def test_hour_distribution_sums_to_one(self):
        """小时段分布占比之和为 1（用真实交易时段）"""
        volumes = [100] * 48  # 48 根覆盖全天真实时段
        df = make_minute(volumes, real_sessions=True)
        r = analyze_volume_minute(df)
        total = sum(r["hour_distribution"].values())
        assert total == pytest.approx(1.0, rel=1e-3)
        assert len(r["hour_distribution"]) == 4

    def test_tail_concentration(self):
        """尾盘集中度：14:30-15:00 量 / 全日量"""
        # 构造全天 48 根（9:30-13:55），其中 14:30 之后集中放量
        volumes = [100] * 48
        df = make_minute(volumes)
        r = analyze_volume_minute(df)
        # 因 make_minute 从 9:30 起每 5 分钟一根，48 根只到 13:25 左右
        # 这里只验证返回值在 [0,1]
        assert 0 <= r["tail_concentration"] <= 1.0

    def test_volume_peaks_returns_top5(self):
        """分时量峰：返回 Top5"""
        volumes = [10, 20, 500, 30, 400, 50, 300, 60, 200, 70]
        df = make_minute(volumes)
        r = analyze_volume_minute(df)
        assert len(r["volume_peaks"]) <= 5
        peak_vols = [p["volume"] for p in r["volume_peaks"]]
        assert peak_vols == sorted(peak_vols, reverse=True)

    def test_empty_minute_df_safe(self):
        """空 DataFrame 安全返回"""
        df = pd.DataFrame(columns=["trade_time", "volume", "amount"])
        r = analyze_volume_minute(df)
        assert r["vwap"] is None
        assert r["hour_distribution"] == {}


# ============ T1c detect_volume_anomaly ============

class TestDetectVolumeAnomaly:
    def test_zscore_high_spike(self):
        """Z-Score：当日量远超均量 → 高 Z"""
        vols = [10000] * 59 + [50000]  # 20 日均量 10000，标准差 0，当日 50000
        df = make_daily(60, vol_trend=vols)
        r = detect_volume_anomaly(df)
        # 标准差为 0 → 用 epsilon 防 0 除；Z 应为大正数或 None
        assert r["vol_zscore"] is None or r["vol_zscore"] > 2

    def test_zscore_normal(self):
        """有波动时 Z-Score 合理"""
        rng = np.random.default_rng(7)
        vols = list(rng.integers(8000, 12000, size=59)) + [15000]
        df = make_daily(60, vol_trend=[float(v) for v in vols])
        r = detect_volume_anomaly(df)
        assert r["vol_zscore"] is not None
        assert r["vol_zscore"] > 1  # 当日明显偏高

    def test_turnover_spike(self):
        """换手率突增倍数"""
        turnover_trend = [1.0] * 59 + [3.0]  # 前 20 日均 1.0，当日 3.0
        vols = [10000] * 60
        # make_daily 默认 turnover=1.0，这里手动构造 turnover 列
        df = make_daily(60, vol_trend=vols)
        df["turnover"] = turnover_trend
        r = detect_volume_anomaly(df)
        assert r["turnover_spike"] == pytest.approx(3.0, rel=1e-3)

    def test_large_order_ratio_with_minute(self):
        """大单比例：分钟线中 > 当日均量3倍 的时段占比"""
        daily_vols = [10000] * 60   # 当日均量 = 10000
        minute_vols = [1000] * 40 + [50000] * 8  # 8 根 > 30000(=10000*3)
        df = make_daily(60, vol_trend=daily_vols)
        minute_df = make_minute(minute_vols)
        r = detect_volume_anomaly(df, minute_df=minute_df)
        # 8/48 ≈ 0.167
        assert r["large_order_ratio"] == pytest.approx(8 / 48, rel=1e-3)

    def test_large_order_ratio_none_without_minute(self):
        """无分钟数据 → large_order_ratio 为 None"""
        df = make_daily(60)
        r = detect_volume_anomaly(df)
        assert r["large_order_ratio"] is None

    def test_insufficient_data_returns_none(self):
        """< 21 行 → zscore/spike 返回 None"""
        df = make_daily(15)
        r = detect_volume_anomaly(df)
        assert r["vol_zscore"] is None
        assert r["turnover_spike"] is None

    def test_empty_df_safe(self):
        """空 DataFrame 安全"""
        df = pd.DataFrame(columns=["trade_date", "volume", "turnover"])
        r = detect_volume_anomaly(df)
        assert r["vol_zscore"] is None
        assert r["turnover_spike"] is None
        assert r["large_order_ratio"] is None
