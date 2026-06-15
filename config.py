"""
配置加载模块 — 从 .env 读取数据库连接信息和股票池
"""
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stock_analysis"),
}

DB_URL = (
    f"mysql+pymysql://{quote_plus(DB_CONFIG['user'])}:{quote_plus(DB_CONFIG['password'])}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset=utf8mb4"
)

STOCK_CODES = [
    code.strip()
    for code in os.getenv("STOCK_CODES", "600519,000858").split(",")
    if code.strip()
]

HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "365"))
MINUTE_PERIOD = os.getenv("MINUTE_PERIOD", "5")

# ===== 定时任务（stock_data_job）=====
JOB_DAILY_CRON = os.getenv("JOB_DAILY_CRON", "30 16 * * 1-5")
JOB_MINUTE_CRON = os.getenv("JOB_MINUTE_CRON", "30 15 * * 1-5")
JOB_LOG_FILE = os.getenv("JOB_LOG_FILE", "stock_data_job.log")

# ===== Web API =====
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# ===== 股池（stock_pool）=====
POOL_CRON = os.getenv("POOL_CRON", "7 9 1 * *")              # 每月1号09:07
POOL_NAME = os.getenv("POOL_NAME", "default")
POOL_MIN_TOTAL_MV = float(os.getenv("POOL_MIN_TOTAL_MV", "30"))        # 总市值(亿)
POOL_MIN_CIRC_MV = float(os.getenv("POOL_MIN_CIRC_MV", "15"))          # 流通市值(亿,近似自由流通)
POOL_MIN_LISTING_DAYS = int(os.getenv("POOL_MIN_LISTING_DAYS", "365")) # 252交易日≈365天
