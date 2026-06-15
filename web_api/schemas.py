"""响应序列化 helper"""
import json

import pandas as pd


def df_records(df: pd.DataFrame) -> list:
    """DataFrame 转 JSON 友好的 dict 列表（处理 date / Decimal / numpy 类型）"""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records"))
