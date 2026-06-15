"""
数据拉取模块 — 通过 akshare 拉取日线、分钟线、股票列表
主源失败/返回空时自动降级到 BaoStock（见 baostock_fetcher.py）
"""
import time
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta

from config import HISTORY_DAYS, MINUTE_PERIOD
from baostock_fetcher import fetch_daily_baostock, fetch_minute_baostock


def fetch_stock_list() -> pd.DataFrame:
    """获取全部 A 股代码和名称"""
    df = ak.stock_zh_a_spot_em()
    return df[["代码", "名称"]].rename(columns={"代码": "stock_code", "名称": "stock_name"})


def _fetch_daily_akshare(stock_code: str, days: int) -> list[dict]:
    """主源 akshare 日线历史数据（前复权），返回 dict 列表"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    df = ak.stock_zh_a_hist(
        symbol=stock_code,
        period="daily",
        start_date=start,
        end_date=end,
        adjust="qfq",
    )
    if df.empty:
        return []

    rename_map = {
        "日期": "trade_date", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount", "涨跌幅": "pct_change", "换手率": "turnover",
    }
    df = df.rename(columns=rename_map)
    df["stock_code"] = stock_code
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date

    keep = ["stock_code", "trade_date", "open", "close", "high", "low",
            "volume", "amount", "pct_change", "turnover"]
    return df[[c for c in keep if c in df.columns]].to_dict("records")


def fetch_daily(stock_code: str, days: int = None) -> list[dict]:
    """
    拉取日线历史数据：主源 akshare，失败/返回空时降级 BaoStock
    主+备均失败时抛异常（交由上层处理，不静默丢数据）
    """
    days = days or HISTORY_DAYS
    try:
        rows = safe_fetch(_fetch_daily_akshare, stock_code, days)
        if rows:
            return rows
        print(f"   ⚠️  {stock_code} 主源返回空，降级 BaoStock")
    except Exception as e:
        print(f"   ⚠️  {stock_code} 主源失败({e})，降级 BaoStock")
    return fetch_daily_baostock(stock_code, days)


def _fetch_minute_akshare(stock_code: str, period: str) -> list[dict]:
    """主源 akshare 分钟线数据（前复权），返回 dict 列表"""
    df = ak.stock_zh_a_hist_min_em(
        symbol=stock_code,
        period=period,
        adjust="qfq",
    )
    if df.empty:
        return []

    rename_map = {
        "时间": "trade_time", "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low", "成交量": "volume",
        "成交额": "amount",
    }
    df = df.rename(columns=rename_map)
    df["stock_code"] = stock_code
    df["trade_date"] = pd.to_datetime(df["trade_time"]).dt.date
    df["trade_time"] = pd.to_datetime(df["trade_time"])
    df["period"] = period

    keep = ["stock_code", "trade_date", "trade_time", "open", "close",
            "high", "low", "volume", "amount", "period"]
    return df[[c for c in keep if c in df.columns]].to_dict("records")


def fetch_minute(stock_code: str, period: str = None) -> list[dict]:
    """
    拉取当天分钟线数据：主源 akshare，失败/返回空时降级 BaoStock
    period: 1 / 5 / 15 / 30 / 60
    主+备均失败时抛异常（交由上层处理，不静默丢数据）
    """
    period = period or MINUTE_PERIOD
    try:
        rows = safe_fetch(_fetch_minute_akshare, stock_code, period)
        if rows:
            return rows
        print(f"   ⚠️  {stock_code} 主源返回空，降级 BaoStock")
    except Exception as e:
        print(f"   ⚠️  {stock_code} 主源失败({e})，降级 BaoStock")
    return fetch_minute_baostock(stock_code, period)


def fetch_realtime(stock_codes: list[str]) -> pd.DataFrame:
    """
    获取实时行情快照（批量）
    返回 DataFrame
    """
    df = ak.stock_zh_a_spot_em()
    df = df[df["代码"].isin(stock_codes)]
    return df


def safe_fetch(func, *args, retries: int = 3, delay: float = 1.0, **kwargs):
    """带重试的拉取包装"""
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i < retries - 1:
                print(f"   重试 {i+1}/{retries}: {e}")
                time.sleep(delay * (i + 1))
            else:
                raise
