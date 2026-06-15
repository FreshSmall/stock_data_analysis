"""
A 股交易日历判断
"""
from datetime import date

import akshare as ak
import pandas as pd

_trade_days = None


def _load_trade_days():
    """加载交易日集合（进程内缓存）"""
    global _trade_days
    if _trade_days is None:
        df = ak.tool_trade_date_hist_sina()
        _trade_days = set(pd.to_datetime(df["trade_date"]).dt.date)
    return _trade_days


def is_trading_day(d: date = None) -> bool:
    """判断指定日期是否为 A 股交易日（默认今天）"""
    d = d or date.today()
    return d in _load_trade_days()
