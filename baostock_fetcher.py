"""
BaoStock 备用数据源 — 主源 akshare 失败/返回空时降级使用

返回与 fetcher 主源一致的 schema，仅依赖 baostock（与 akshare 不同源，
真正起到降级作用）。纯逻辑（代码转换、行解析）与网络层分离，便于离线单测。
"""
from datetime import datetime, timedelta

import baostock as bs

# BaoStock 日线字段顺序（与 _parse_daily_row 的索引一一对应）
_DAILY_FIELDS = "date,code,open,high,low,close,volume,amount,turn,pctChg"
# BaoStock 分钟线字段顺序
_MINUTE_FIELDS = "date,time,code,open,high,low,close,volume,amount"


def _to_bs_code(stock_code: str) -> str:
    """纯数字股票代码 → BaoStock 带交易所前缀代码

    6 开头 → sh（沪市主板/科创板），0/3 开头 → sz（深市主板/中小板/创业板）
    """
    code = str(stock_code).strip()
    if code.startswith("6"):
        return f"sh.{code}"
    if code.startswith(("0", "3")):
        return f"sz.{code}"
    raise ValueError(f"无法识别的股票代码: {stock_code}（暂仅支持沪/深主板）")


def _f(value: str) -> float:
    """BaoStock 数值为字符串，安全转 float（空值/异常 → 0.0）"""
    try:
        return float(value) if value else 0.0
    except (TypeError, ValueError):
        return 0.0


def _parse_daily_row(row: list, stock_code: str) -> dict:
    """单行 BaoStock 日线 → schema dict（按 _DAILY_FIELDS 顺序取值）"""
    return {
        "stock_code": stock_code,
        "trade_date": datetime.strptime(row[0], "%Y-%m-%d").date(),
        "open": _f(row[2]),
        "high": _f(row[3]),
        "low": _f(row[4]),
        "close": _f(row[5]),
        "volume": _f(row[6]),
        "amount": _f(row[7]),
        "turnover": _f(row[8]),
        "pct_change": _f(row[9]),
    }


def _parse_minute_row(row: list, stock_code: str, period: str) -> dict:
    """单行 BaoStock 分钟线 → schema dict

    time 格式 yyyyMMddHHmmssSSS（17 位含毫秒），用 %f 解析。
    """
    trade_time = datetime.strptime(row[1], "%Y%m%d%H%M%S%f")
    return {
        "stock_code": stock_code,
        "trade_date": trade_time.date(),
        "trade_time": trade_time,
        "period": period,
        "open": _f(row[3]),
        "high": _f(row[4]),
        "low": _f(row[5]),
        "close": _f(row[6]),
        "volume": _f(row[7]),
        "amount": _f(row[8]),
    }


def _query(bs_code: str, fields: str, start: str, end: str,
           frequency: str, adjustflag: str = "2") -> list:
    """封装 login → query → logout，返回原始行列表（每行为字段值列表）

    adjustflag=2 前复权，与主源 akshare 的 qfq 口径一致。
    """
    lg = bs.login()
    if getattr(lg, "error_code", "0") != "0":
        raise RuntimeError(f"BaoStock login 失败: {getattr(lg, 'error_msg', 'unknown')}")
    try:
        rs = bs.query_history_k_data_plus(
            bs_code, fields,
            start_date=start, end_date=end,
            frequency=frequency, adjustflag=adjustflag,
        )
        if rs is None:
            raise RuntimeError("BaoStock query 返回空（检查日期格式/参数）")
        if getattr(rs, "error_code", "0") != "0":
            raise RuntimeError(f"BaoStock query 失败: {getattr(rs, 'error_msg', 'unknown')}")
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        return rows
    finally:
        bs.logout()


def fetch_daily_baostock(stock_code: str, days: int) -> list:
    """BaoStock 日线（前复权）→ schema dict 列表"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = _query(_to_bs_code(stock_code), _DAILY_FIELDS,
                  start, end, frequency="d", adjustflag="2")
    return [_parse_daily_row(r, stock_code) for r in rows]


def fetch_minute_baostock(stock_code: str, period: str) -> list:
    """BaoStock 分钟线（前复权）→ schema dict 列表

    注意：BaoStock 分钟线仅最近约 5 个交易日可用；取 10 天窗口覆盖最近交易日。
    """
    now = datetime.now()
    # BaoStock 分钟线日期格式为 "yyyy-MM-dd"（纯日期，带时分秒会报"日期格式不正确"）
    end = now.strftime("%Y-%m-%d")
    start = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    rows = _query(_to_bs_code(stock_code), _MINUTE_FIELDS,
                  start, end, frequency=str(period), adjustflag="2")
    return [_parse_minute_row(r, stock_code, str(period)) for r in rows]
