"""
数据分析模块 — 均线、RSI、MACD、金叉检测、涨跌统计
"""
import pandas as pd

from data.db import query_daily


# ==================== 技术指标 ====================

def calc_ma(df: pd.DataFrame, col: str = "close") -> pd.DataFrame:
    """计算均线 MA5/10/20/60"""
    df = df.copy()
    for w in [5, 10, 20, 60]:
        df[f"ma{w}"] = df[col].rolling(window=w).mean()
    return df


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """计算 RSI"""
    df = df.copy()
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))
    return df


def calc_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
    """计算 MACD"""
    df = df.copy()
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    df["dif"] = ema_fast - ema_slow
    df["dea"] = df["dif"].ewm(span=signal, adjust=False).mean()
    df["macd"] = (df["dif"] - df["dea"]) * 2
    return df


def detect_golden_cross(df: pd.DataFrame) -> list[dict]:
    """检测 MA5 × MA20 金叉"""
    df = calc_ma(df)
    condition = (df["ma5"] > df["ma20"]) & (df["ma5"].shift(1) <= df["ma20"].shift(1))
    hits = df[condition][["trade_date", "close", "ma5", "ma20"]]
    return hits.to_dict("records")


def detect_macd_cross(df: pd.DataFrame) -> list[dict]:
    """检测 MACD 金叉/死叉"""
    df = calc_macd(df)
    golden = (df["dif"] > df["dea"]) & (df["dif"].shift(1) <= df["dea"].shift(1))
    death = (df["dif"] < df["dea"]) & (df["dif"].shift(1) >= df["dea"].shift(1))

    results = []
    for _, row in df[golden].iterrows():
        results.append({"date": str(row["trade_date"]), "type": "金叉", "close": float(row["close"])})
    for _, row in df[death].iterrows():
        results.append({"date": str(row["trade_date"]), "type": "死叉", "close": float(row["close"])})
    results.sort(key=lambda x: x["date"])
    return results


# ==================== 报告输出 ====================

def print_report(stock_code: str):
    """打印单只股票分析报告"""
    df = query_daily(stock_code)
    if df.empty:
        print(f"❌ {stock_code} 无数据")
        return

    print(f"\n{'='*60}")
    print(f"📊 {stock_code} 分析报告")
    print(f"{'='*60}")

    # 基础统计
    latest = df.iloc[-1]
    print(f"\n  📈 行情概况:")
    print(f"    最新日期:  {latest['trade_date']}")
    print(f"    最新收盘:  {latest['close']}")
    print(f"    区间最高:  {df['high'].max()}")
    print(f"    区间最低:  {df['low'].min()}")
    print(f"    区间均价:  {df['close'].mean():.2f}")
    if "pct_change" in df.columns:
        print(f"    日均涨跌:  {df['pct_change'].mean():.4f}%")

    # 均线
    df = calc_ma(df)
    print(f"\n  📊 均线:")
    for w in [5, 10, 20, 60]:
        col = f"ma{w}"
        if pd.notna(latest.get(col)):
            print(f"    MA{w}: {latest[col]:.2f}")

    # RSI
    df = calc_rsi(df)
    rsi_val = df.iloc[-1].get("rsi")
    if pd.notna(rsi_val):
        tag = "超买 ⚠️" if rsi_val > 70 else "超卖 🔥" if rsi_val < 30 else "中性"
        print(f"\n  📉 RSI(14): {rsi_val:.1f} → {tag}")

    # MACD
    df = calc_macd(df)
    last_macd = df.iloc[-1]
    macd_val = last_macd["macd"]
    print(f"\n  📉 MACD:")
    print(f"    DIF:  {last_macd['dif']:.4f}")
    print(f"    DEA:  {last_macd['dea']:.4f}")
    print(f"    柱:   {macd_val:+.4f}  {'🔴' if macd_val > 0 else '🟢'}")

    # 金叉信号
    gc = detect_golden_cross(df)
    if gc:
        print(f"\n  ✨ 最近 MA 金叉: {gc[-1]['trade_date']}  价格 {gc[-1]['close']}")

    mc = detect_macd_cross(df)
    if mc:
        last_mc = mc[-1]
        print(f"  ✨ 最近 MACD {'金叉' if last_mc['type']=='金叉' else '死叉'}: {last_mc['date']}  价格 {last_mc['close']}")

    print(f"\n{'='*60}")


def calc_report(stock_code: str) -> dict:
    """返回结构化分析数据（供 web/api 使用）"""
    df = query_daily(stock_code)
    if df.empty:
        return {"stock_code": stock_code, "error": "无数据"}

    df = calc_ma(df)
    df = calc_rsi(df)
    df = calc_macd(df)
    last = df.iloc[-1]

    def _f(v):
        return float(v) if pd.notna(v) else None

    return {
        "stock_code": stock_code,
        "latest_date": str(last["trade_date"]),
        "latest_close": _f(last["close"]),
        "range": {
            "high": _f(df["high"].max()),
            "low": _f(df["low"].min()),
            "avg_close": _f(df["close"].mean()),
            "avg_pct_change": _f(df["pct_change"].mean()) if "pct_change" in df else None,
        },
        "ma": {f"ma{w}": _f(last.get(f"ma{w}")) for w in [5, 10, 20, 60]},
        "rsi": _f(last.get("rsi")),
        "macd": {"dif": _f(last["dif"]), "dea": _f(last["dea"]), "hist": _f(last["macd"])},
        "golden_cross": detect_golden_cross(df)[-1:],
        "macd_signal": detect_macd_cross(df)[-1:],
    }
