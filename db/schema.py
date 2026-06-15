"""
建表 DDL — daily_prices / minute_prices / stocks
"""
from sqlalchemy import text

from .connection import get_engine


def init_db():
    """创建 daily_prices 和 minute_prices 表"""
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_prices (
                id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code  VARCHAR(10)   NOT NULL,
                trade_date  DATE          NOT NULL,
                open        DECIMAL(10,2),
                close       DECIMAL(10,2),
                high        DECIMAL(10,2),
                low         DECIMAL(10,2),
                volume      BIGINT,
                amount      DECIMAL(18,2),
                pct_change  DECIMAL(8,4),
                turnover    DECIMAL(8,4),
                UNIQUE KEY uk_code_date (stock_code, trade_date),
                INDEX idx_date (trade_date),
                INDEX idx_code (stock_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS minute_prices (
                id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code  VARCHAR(10)   NOT NULL,
                trade_date  DATE          NOT NULL,
                trade_time  DATETIME      NOT NULL,
                open        DECIMAL(10,2),
                close       DECIMAL(10,2),
                high        DECIMAL(10,2),
                low         DECIMAL(10,2),
                volume      BIGINT,
                amount      DECIMAL(18,2),
                period      VARCHAR(4)   DEFAULT '5',
                UNIQUE KEY uk_code_time (stock_code, trade_time, period),
                INDEX idx_date (trade_date),
                INDEX idx_code (stock_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stocks (
                stock_code  VARCHAR(10) PRIMARY KEY,
                stock_name  VARCHAR(50),
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_runs (
                id            BIGINT AUTO_INCREMENT PRIMARY KEY,
                job_name      VARCHAR(50)  NOT NULL,
                started_at    DATETIME     NOT NULL,
                finished_at   DATETIME,
                status        VARCHAR(20)  NOT NULL,
                rows_affected BIGINT,
                error         TEXT,
                INDEX idx_job_started (job_name, started_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_pool (
                id            BIGINT AUTO_INCREMENT PRIMARY KEY,
                pool_name     VARCHAR(50)  NOT NULL COMMENT '股池名称(筛选器版本,默认default)',
                trade_date    DATE         NOT NULL COMMENT '筛选日期/期次',
                stock_code    VARCHAR(10)  NOT NULL,
                stock_name    VARCHAR(50),
                exchange      VARCHAR(10)  COMMENT '交易所:上海/深圳/北交所',
                close         DECIMAL(12,3) COMMENT '筛选时现价',
                pct_change    DECIMAL(8,4)  COMMENT '当日涨跌幅%',
                total_mv      DECIMAL(14,2) COMMENT '总市值(亿)',
                circ_mv       DECIMAL(14,2) COMMENT '流通市值近似(亿,新浪nmc近似自由流通)',
                turnover      DECIMAL(10,4) COMMENT '换手率%',
                pe            DECIMAL(12,3),
                pb            DECIMAL(12,3),
                list_date     DATE          COMMENT '上市日期',
                audit_opinion VARCHAR(50)   DEFAULT '未校验' COMMENT '审计意见(暂未校验)',
                created_at    DATETIME      DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_pool_date_code (pool_name, trade_date, stock_code),
                INDEX idx_pool_date (pool_name, trade_date),
                INDEX idx_code (stock_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='股池筛选结果快照'
        """))

        conn.commit()
    print("✅ 数据库初始化完成: daily_prices, minute_prices, stocks, job_runs, stock_pool")
