from datetime import datetime, date

import pytest

from baostock_fetcher import _to_bs_code, _f, _parse_daily_row, _parse_minute_row


def test_to_bs_code_sh():
    assert _to_bs_code("600519") == "sh.600519"
    assert _to_bs_code("688981") == "sh.688981"


def test_to_bs_code_sz():
    assert _to_bs_code("000001") == "sz.000001"
    assert _to_bs_code("300750") == "sz.300750"


def test_to_bs_code_invalid():
    with pytest.raises(ValueError):
        _to_bs_code("830789")  # 北交所，暂不支持


def test_f_handles_empty_and_garbage():
    assert _f("") == 0.0
    assert _f(None) == 0.0
    assert _f("abc") == 0.0
    assert _f("123.45") == 123.45


def test_parse_daily_row():
    # BaoStock 日线 fields 顺序：date,code,open,high,low,close,volume,amount,turn,pctChg
    row = ["2026-06-13", "sh.600519", "1680.00", "1699.99", "1670.00",
           "1695.50", "12345.0", "2089000000.0", "0.98", "1.23"]
    d = _parse_daily_row(row, "600519")
    assert d["stock_code"] == "600519"
    assert d["trade_date"] == date(2026, 6, 13)
    assert d["open"] == 1680.00
    assert d["close"] == 1695.50
    assert d["volume"] == 12345.0
    assert d["amount"] == 2089000000.0
    assert d["turnover"] == 0.98
    assert d["pct_change"] == 1.23


def test_parse_minute_row():
    # BaoStock 分钟 fields 顺序：date,time,code,open,high,low,close,volume,amount
    row = ["2026-06-13", "20260613093500000", "sh.600519",
           "1680.00", "1685.00", "1678.00", "1683.00", "1500.0", "2520000.0"]
    m = _parse_minute_row(row, "600519", "5")
    assert m["stock_code"] == "600519"
    assert m["trade_date"] == date(2026, 6, 13)
    assert m["trade_time"] == datetime(2026, 6, 13, 9, 35, 0)
    assert m["period"] == "5"
    assert m["close"] == 1683.00
    assert m["volume"] == 1500.0


def test_query_returns_none_raises(monkeypatch):
    """BaoStock query 返回 None（日期/参数错误）时应抛 RuntimeError，而非 NoneType 崩溃"""
    import baostock as bs
    import baostock_fetcher

    monkeypatch.setattr(bs, "login", lambda: type("R", (), {"error_code": "0"})())
    monkeypatch.setattr(bs, "query_history_k_data_plus", lambda *a, **kw: None)
    monkeypatch.setattr(bs, "logout", lambda: None)
    with pytest.raises(RuntimeError, match="返回空"):
        baostock_fetcher._query(
            "sh.600519", "date,close",
            "2026-06-01", "2026-06-15", "d",
        )
