# -*- coding: utf-8 -*-
"""
A股股池筛选器（模块化）

筛选条件：
  1. 非ST/非退市          ✅ 名称判断
  2. 上市满252交易日      ✅ datacenter LISTING_DATE，365日历天近似
  3. 20日均成交额>5000万  ⏭️ 跳过(需历史日线)
  4. 60日均换手率>0.3%    ⏭️ 跳过
  5. 总市值>30亿          ✅ 新浪 mktcap
  6. 自由流通市值>15亿    ✅ 流通市值 nmc 近似(标注)
  7. 60日涨跌停占比<15%   ⏭️ 跳过
  8. 审计意见标准无保留   ⏳ 留"未校验"
  9. 非B股                ✅ 新浪 hs_a 列表本身不含纯B股

数据源：
  - 新浪 getHQNodeData(node=hs_a)：全市场行情+市值+换手率(沪深+北交所)
  - 东财 datacenter RPT_F10_BASIC_ORGINFO：批量上市日期 LISTING_DATE

对外接口（CLI / Job / API 共用）：
  - fetch_and_filter(trade_date) -> list[dict]  核心筛选，返回表字段记录
  - run_pool(...) -> int                        编排：筛选 + 入库(+CSV)
  - python a_stock_filter.py [--db]             CLI（默认CSV，--db 加入库）

注意：本机系统代理 127.0.0.1:7897 对数据源转发不稳定，
      所有请求强制直连(proxies=None)+重试。
阈值读 config(POOL_*)，单位亿；内部换算为万元(与新浪字段一致)。
"""
import os
import sys
import json
import time
import datetime
from typing import Optional, List, Dict, Any

import pandas as pd
import requests

from config import POOL_MIN_TOTAL_MV, POOL_MIN_CIRC_MV, POOL_MIN_LISTING_DAYS

# ============== 配置 ==============
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# 阈值(单位:万元，与新浪字段一致)；config 单位为亿，这里换算
THRESH_MKTCAP = POOL_MIN_TOTAL_MV * 10000      # 亿 -> 万元
THRESH_NMC = POOL_MIN_CIRC_MV * 10000
THRESH_LISTING_DAYS = POOL_MIN_LISTING_DAYS    # 252交易日≈365日历天

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

# 强制直连：绕过本机失效的系统代理
NO_PROXY = {"http": None, "https": None}
HEADERS = {"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"}
HEADERS_EM = {"User-Agent": UA, "Referer": "https://emweb.eastmoney.com/"}


def _get(url, headers, params=None, tries=4, sleep=0.6) -> Optional[requests.Response]:
    """带重试的直连 GET。"""
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, params=params,
                             timeout=15, proxies=NO_PROXY)
            if r.status_code == 200 and r.text:
                return r
        except Exception:
            pass
        time.sleep(sleep * (i + 1))
    return None


# ============== 数据拉取 ==============
def fetch_sina_all() -> pd.DataFrame:
    """新浪分页拉全市场A股(含沪深+北交所)。返回 DataFrame。"""
    url = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/"
           "json_v2.php/Market_Center.getHQNodeData")
    page, num = 1, 80
    all_rows = []
    while True:
        params = {"page": page, "num": num, "sort": "symbol",
                  "asc": 1, "node": "hs_a", "symbol": "", "_s_r_a": "sort"}
        r = _get(url, HEADERS, params)
        if r is None:
            print(f"  [warn] 新浪第{page}页拉取失败,重试耗尽,停止")
            break
        rows = json.loads(r.text)
        if not rows:
            break
        all_rows.extend(rows)
        if page % 10 == 0:
            print(f"  已拉取 {len(all_rows)} 条 (page {page})")
        page += 1
        time.sleep(0.25)
    df = pd.DataFrame(all_rows)
    print(f"  新浪全市场拉取完成: {len(df)} 条")
    return df


def fetch_em_basic_batch(codes: List[str], batch_size: int = 50) -> Dict[str, Dict[str, Any]]:
    """东财datacenter批量查上市日期+B股标识+行业。codes: 6位代码列表。
    返回 {code: {"list_date": "YYYY-MM-DD", "has_b": bool, "industry": "行业"}}。"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    result = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        code_in = ",".join(f'"{c}"' for c in batch)
        params = {
            "reportName": "RPT_F10_BASIC_ORGINFO",
            "columns": "SECURITY_CODE,LISTING_DATE,STR_CODEB,INDUSTRYCSRC1",
            "filter": f"(SECURITY_CODE in ({code_in}))",
            "pageSize": str(batch_size),
            "pageNumber": "1",
        }
        r = _get(url, HEADERS, params)
        if r is None:
            print(f"  [warn] datacenter 批次 {i // batch_size + 1} 失败,跳过")
            time.sleep(0.4)
            continue
        try:
            data = (r.json().get("result") or {}).get("data") or []
        except Exception:
            data = []
        for row in data:
            code = str(row.get("SECURITY_CODE"))
            ld = row.get("LISTING_DATE")
            list_date = str(ld)[:10] if ld else None
            # INDUSTRYCSRC1 格式如 "金融业-货币金融服务"，取大类（首段）
            industry_raw = row.get("INDUSTRYCSRC1") or ""
            industry = industry_raw.split("-")[0].strip() if industry_raw else None
            result[code] = {"list_date": list_date,
                            "has_b": bool(row.get("STR_CODEB")),
                            "industry": industry}
        time.sleep(0.2)
    return result


def is_st(name: str) -> bool:
    if not name:
        return False
    n = name.upper().replace(" ", "")
    return "ST" in n or "退" in name


def prefix_of(symbol: str):
    """新浪 symbol(sh600000) -> 交易所前缀 SH/SZ/BJ + 中文。"""
    s = symbol.lower()
    if s.startswith("sh"):
        return "SH", "上海"
    if s.startswith("sz"):
        return "SZ", "深圳"
    if s.startswith("bj"):
        return "BJ", "北交所"
    return "", "其他"


def _to_date(d) -> datetime.date:
    """trade_date 容器统一为 date：None=今天 / date / 'YYYY-MM-DD'。"""
    if d is None:
        return datetime.date.today()
    if isinstance(d, datetime.date):
        return d
    return datetime.date.fromisoformat(str(d)[:10])


# ============== 核心：筛选 ==============
def fetch_and_filter(trade_date=None) -> List[Dict[str, Any]]:
    """核心筛选，返回结构化快照记录列表（字段对应 stock_pool 表，不含 pool_name/trade_date 元数据）。
    trade_date: 筛选基准日(date / 'YYYY-MM-DD' / None=今天)。"""
    base = _to_date(trade_date)

    print("[1/3] 拉取新浪全市场行情...")
    raw = fetch_sina_all()
    if raw.empty:
        print("  拉取失败，返回空")
        return []

    for c in ["mktcap", "nmc", "turnoverratio", "per", "pb", "trade", "changepercent"]:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw["code6"] = raw["code"].astype(str)

    print("[2/3] 粗筛(非ST/总市值/流通市值)...")
    raw["is_st"] = raw["name"].apply(is_st)
    coarse = raw[(~raw["is_st"]) &
                 (raw["mktcap"] > THRESH_MKTCAP) &
                 (raw["nmc"] > THRESH_NMC)].copy()
    print(f"  粗筛后: {len(coarse)} / {len(raw)}")

    print(f"[3/3] datacenter补上市日期 + 精筛(上市满{THRESH_LISTING_DAYS}天)...")
    basic = fetch_em_basic_batch(list(coarse["code6"]))

    records = []
    for row in coarse.itertuples(index=False):
        _, exch = prefix_of(row.symbol)
        info = basic.get(row.code6, {})
        list_date = info.get("list_date")
        list_days = None
        if list_date:
            try:
                list_days = (base - datetime.date.fromisoformat(list_date)).days
            except Exception:
                list_days = None
        # 上市满阈值；拿不到日期的(极少)保留，不误杀
        if list_days is not None and list_days < THRESH_LISTING_DAYS:
            continue
        records.append({
            "stock_code": row.code6,
            "stock_name": row.name,
            "exchange": exch,
            "industry": info.get("industry"),
            "close": row.trade,
            "pct_change": row.changepercent,
            "total_mv": round(row.mktcap / 10000, 2),
            "circ_mv": round(row.nmc / 10000, 2),
            "turnover": row.turnoverratio,
            "pe": row.per,
            "pb": row.pb,
            "list_date": list_date,
            "audit_opinion": "未校验",
        })
    records.sort(key=lambda r: r.get("total_mv") or 0, reverse=True)
    print(f"  符合条件: {len(records)} 只")
    return records


# ============== 编排：入库 + CSV ==============
def run_pool(trade_date=None, pool_name="default",
             save_db=True, save_csv=False) -> int:
    """编排：拉取筛选 → (可选)入库 → (可选)CSV。返回命中条数。
    - trade_date: 筛选期次日(None=今天)
    - save_db=True 调 db.upsert_rows 入 stock_pool（同期重跑幂等覆盖）
    - save_csv=True 仍写 output/a_stock_filtered_YYYYMMDD.csv（向后兼容）
    """
    base = _to_date(trade_date)
    print(f"=== 股池筛选 pool={pool_name} trade_date={base} ===")
    records = fetch_and_filter(base)
    if not records:
        return 0

    for r in records:
        r["pool_name"] = pool_name
        r["trade_date"] = base

    n = len(records)
    if save_db:
        from db import upsert_rows
        affected = upsert_rows(records, "stock_pool",
                               ["pool_name", "trade_date", "stock_code"])
        print(f"入库 stock_pool: {affected} 条 (pool={pool_name}, date={base})")
    if save_csv:
        os.makedirs(OUT_DIR, exist_ok=True)
        out_csv = os.path.join(OUT_DIR, f"a_stock_filtered_{base.strftime('%Y%m%d')}.csv")
        pd.DataFrame(records).to_csv(out_csv, index=False, encoding="utf-8-sig")
        print(f"CSV: {out_csv}")
    return n


def main():
    """CLI：python a_stock_filter.py [--db]   默认输出CSV；--db 同时入库"""
    save_db = "--db" in sys.argv
    n = run_pool(save_db=save_db, save_csv=True)
    print(f"\n完成: {n} 只")


if __name__ == "__main__":
    main()
