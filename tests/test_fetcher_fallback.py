import pytest

import fetcher


def test_no_fallback_when_primary_ok(monkeypatch):
    """主源正常 → 不调备用"""
    called = {"backup": False}

    def fake_primary(code, days):
        return [{"stock_code": code, "trade_date": "2026-06-13", "volume": 100}]

    def fake_backup(code, days):
        called["backup"] = True
        return []

    monkeypatch.setattr(fetcher, "_fetch_daily_akshare", fake_primary)
    monkeypatch.setattr(fetcher, "fetch_daily_baostock", fake_backup)
    rows = fetcher.fetch_daily("600519")
    assert rows == [{"stock_code": "600519", "trade_date": "2026-06-13", "volume": 100}]
    assert called["backup"] is False


def test_fallback_when_primary_empty(monkeypatch):
    """主源返回空 → 降级备用"""
    monkeypatch.setattr(fetcher, "_fetch_daily_akshare", lambda c, d: [])
    monkeypatch.setattr(fetcher, "fetch_daily_baostock",
                        lambda c, d: [{"stock_code": c, "volume": 1}])
    rows = fetcher.fetch_daily("600519")
    assert rows == [{"stock_code": "600519", "volume": 1}]


def test_fallback_when_primary_raises(monkeypatch):
    """主源抛异常 → 降级备用"""
    def boom(c, d):
        raise RuntimeError("akshare down")

    monkeypatch.setattr(fetcher, "_fetch_daily_akshare", boom)
    monkeypatch.setattr(fetcher, "fetch_daily_baostock",
                        lambda c, d: [{"stock_code": c, "volume": 1}])
    rows = fetcher.fetch_daily("600519")
    assert len(rows) == 1


def test_both_fail_raises(monkeypatch):
    """主+备都失败 → 抛异常（不静默吞错）"""

    def bs_boom(c, d):
        raise RuntimeError("bs down")

    monkeypatch.setattr(fetcher, "_fetch_daily_akshare", lambda c, d: [])
    monkeypatch.setattr(fetcher, "fetch_daily_baostock", bs_boom)
    with pytest.raises(RuntimeError):
        fetcher.fetch_daily("600519")


def test_minute_fallback(monkeypatch):
    """分钟线降级同构"""
    monkeypatch.setattr(fetcher, "_fetch_minute_akshare", lambda c, p: [])
    monkeypatch.setattr(fetcher, "fetch_minute_baostock",
                        lambda c, p: [{"stock_code": c, "period": p}])
    rows = fetcher.fetch_minute("600519")
    assert rows == [{"stock_code": "600519", "period": "5"}]
