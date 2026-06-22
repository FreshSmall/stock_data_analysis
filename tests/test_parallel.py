"""测试多进程并发拉取 BaoStock（需独立文件，macOS spawn 模式要求）"""
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from data.fetchers.baostock_fetcher import fetch_daily_baostock
from data.db import get_engine
from sqlalchemy import text


def fetch_one(code):
    """进程级独立 login/logout（每个进程有自己的 BaoStock 连接）"""
    try:
        rows = fetch_daily_baostock(code, days=365)
        return code, len(rows) if rows else 0
    except Exception as e:
        return code, f"ERR: {str(e)[:60]}"


def main():
    e = get_engine()
    with e.connect() as c:
        rows = c.execute(text("""
            SELECT sp.stock_code FROM stock_pool sp
            LEFT JOIN (SELECT DISTINCT stock_code FROM daily_prices) d ON sp.stock_code = d.stock_code
            WHERE d.stock_code IS NULL AND sp.trade_date = (SELECT MAX(trade_date) FROM stock_pool)
            ORDER BY sp.stock_code LIMIT 8
        """)).fetchall()
    codes = [r[0] for r in rows]
    print(f'测试 {len(codes)} 只: {codes}')

    print('\n--- 4 进程并发 ---')
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one, code): code for code in codes}
        results = {}
        for f in as_completed(futures):
            c, n = f.result()
            results[c] = n
    parallel_time = time.time() - t0

    success = sum(1 for v in results.values() if isinstance(v, int) and v > 0)
    print(f'并发 8 只: {parallel_time:.1f}s ({parallel_time/8:.2f}s/只)')
    print(f'成功: {success}/8')
    for c, n in sorted(results.items()):
        print(f'  {c}: {n}')
    print(f'\n预估 3597 只: {3597*parallel_time/8/60:.0f} 分钟 ({3597*parallel_time/8/3600:.1f} 小时)')


if __name__ == "__main__":
    main()
