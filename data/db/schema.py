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
                industry      VARCHAR(50)  COMMENT '行业大类(证监会分类首段)',
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

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_signal (
                id              BIGINT AUTO_INCREMENT PRIMARY KEY,
                signal_date     DATE         NOT NULL COMMENT '信号日期',
                stock_code      VARCHAR(10)  NOT NULL,
                stock_name      VARCHAR(50),
                score           DECIMAL(5,2) NOT NULL COMMENT '综合评分 0-100',
                label           VARCHAR(20)  NOT NULL COMMENT '强烈关注/值得关注/中性观察/暂不参与',
                -- 量价维度
                vol_ratio       DECIMAL(8,4) COMMENT '量比',
                vol_zscore      DECIMAL(8,4) COMMENT '成交量Z-Score',
                vol_price_trend VARCHAR(20)  COMMENT '量价关系:同向多/同向空/顶背离/底背离/中性',
                obv_signal      VARCHAR(20)  COMMENT 'OBV信号:新高/新低/持平',
                vr_value        DECIMAL(8,2) COMMENT 'VR容量比率',
                breakout        TINYINT(1)   DEFAULT 0 COMMENT '是否放量突破',
                pullback        TINYINT(1)   DEFAULT 0 COMMENT '是否缩量回踩',
                -- 价格维度
                ma_trend        VARCHAR(20)  COMMENT '均线趋势:多头/空头/缠绕',
                macd_signal     VARCHAR(20)  COMMENT 'MACD信号:金叉/死叉/红柱/绿柱',
                rsi_value       DECIMAL(6,2),
                golden_cross    TINYINT(1)   DEFAULT 0 COMMENT '当日是否MA金叉',
                -- 分时维度
                vwap            DECIMAL(12,3) COMMENT '当日VWAP',
                vwap_deviation  DECIMAL(8,4)  COMMENT '收盘价相对VWAP偏离%',
                tail_concentration DECIMAL(8,4) COMMENT '尾盘集中度%',
                -- 分项得分
                score_vol_price DECIMAL(5,2) COMMENT '量价配合得分',
                score_trend     DECIMAL(5,2) COMMENT '趋势方向得分',
                score_momentum  DECIMAL(5,2) COMMENT '动量信号得分',
                score_anomaly   DECIMAL(5,2) COMMENT '异动检测得分',
                score_intraday  DECIMAL(5,2) COMMENT '分时确认得分',
                -- 元数据
                reason          TEXT          COMMENT '信号理由(自然语言摘要)',
                created_at      DATETIME      DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_signal_date_code (signal_date, stock_code),
                INDEX idx_signal_date_score (signal_date, score DESC),
                INDEX idx_signal_date_label (signal_date, label),
                INDEX idx_code (stock_code)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每日成交量分析信号快照'
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stock_signal_log (
                id              BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code      VARCHAR(10)  NOT NULL,
                signal_date     DATE         NOT NULL,
                score           DECIMAL(5,2) NOT NULL,
                label           VARCHAR(20)  NOT NULL,
                action          VARCHAR(20)  COMMENT '建议动作:关注/加仓/减仓/清仓/无',
                next_5d_return  DECIMAL(8,4) COMMENT '5日后收益率%(异步回填)',
                next_20d_return DECIMAL(8,4) COMMENT '20日后收益率%(异步回填)',
                created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_code_date (stock_code, signal_date),
                INDEX idx_date_score (signal_date, score DESC)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信号历史与回测追踪'
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chip_distribution (
                id                BIGINT AUTO_INCREMENT PRIMARY KEY,
                stock_code        VARCHAR(10)   NOT NULL,
                trade_date        DATE          NOT NULL COMMENT '交易日',
                profit_ratio      DECIMAL(8,6)  COMMENT '获利比例 0-1(当前价下方筹码占比)',
                avg_cost          DECIMAL(12,3) COMMENT '平均成本(50%筹码对应价位)',
                cost_90_low       DECIMAL(12,3) COMMENT '90%筹码下沿',
                cost_90_high      DECIMAL(12,3) COMMENT '90%筹码上沿',
                concentration_90  DECIMAL(8,4)  COMMENT '90%集中度=(高-低)/(高+低)',
                cost_70_low       DECIMAL(12,3) COMMENT '70%筹码下沿',
                cost_70_high      DECIMAL(12,3) COMMENT '70%筹码上沿',
                concentration_70  DECIMAL(8,4)  COMMENT '70%集中度=(高-低)/(高+低)',
                distribution      TEXT          COMMENT '筹码分布JSON数组[(price,weight),...]',
                updated_at        DATETIME      DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_code_date (stock_code, trade_date),
                INDEX idx_code_date (stock_code, trade_date),
                INDEX idx_date (trade_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='筹码分布(本地复现东方财富CYQ算法)'
        """))

        # stock_pool 表补充 industry 列（已存在表不会重建，需 ALTER）
        try:
            conn.execute(text(
                "ALTER TABLE stock_pool ADD COLUMN industry VARCHAR(50) "
                "COMMENT '行业大类(证监会分类首段)' AFTER exchange"
            ))
            print("  stock_pool 新增 industry 列")
        except Exception:
            pass  # 列已存在

        # stock_signal 表补充筹码维度列（已存在表不会重建，需 ALTER）
        for ddl in (
            "ALTER TABLE stock_signal ADD COLUMN chip_profit_ratio DECIMAL(8,6) "
            "COMMENT '获利比例0-1' AFTER tail_concentration",
            "ALTER TABLE stock_signal ADD COLUMN chip_concentration DECIMAL(8,4) "
            "COMMENT '90%筹码集中度' AFTER chip_profit_ratio",
            "ALTER TABLE stock_signal ADD COLUMN chip_avg_cost DECIMAL(12,3) "
            "COMMENT '筹码平均成本' AFTER chip_concentration",
            "ALTER TABLE stock_signal ADD COLUMN chip_label VARCHAR(20) "
            "COMMENT '筹码标签:筹码锁定/筹码收敛/筹码分散/获利盘堆积' AFTER chip_avg_cost",
            "ALTER TABLE stock_signal ADD COLUMN chip_bonus DECIMAL(5,2) "
            "COMMENT '筹码调整分(-5~+5)' AFTER chip_label",
        ):
            try:
                conn.execute(text(ddl))
                print(f"  stock_signal 新增列: {ddl.split('ADD COLUMN')[1].split()[0]}")
            except Exception:
                pass  # 列已存在

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS screen_result (
                id            BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id        VARCHAR(40)  NOT NULL COMMENT '漏斗执行批次ID(日期+预设)',
                run_date      DATE         NOT NULL COMMENT '执行日期',
                layer         TINYINT      NOT NULL COMMENT '层级: 1=粗筛 2=精筛',
                preset        VARCHAR(20)  NOT NULL COMMENT '粗筛预设: value/growth/...',
                strategy      VARCHAR(20)  COMMENT '精筛策略: trend/breakout/...(layer=2)',
                stock_code    VARCHAR(10)  NOT NULL,
                stock_name    VARCHAR(50),
                exchange      VARCHAR(10)  COMMENT '交易所',
                total_mv      DECIMAL(14,2) COMMENT '总市值(亿)',
                pe            DECIMAL(12,3),
                pb            DECIMAL(12,3),
                turnover      DECIMAL(10,4) COMMENT '换手率%',
                pct_change    DECIMAL(8,4)  COMMENT '涨跌幅%',
                industry      VARCHAR(50),
                `match`       TINYINT(1)   COMMENT '是否策略命中(layer2)',
                score         DECIMAL(5,2) COMMENT '策略得分',
                reason        TEXT         COMMENT '策略理由',
                vol_ratio     DECIMAL(8,4),
                macd_signal   VARCHAR(20),
                rsi_value     DECIMAL(6,2),
                created_at    DATETIME      DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_run_layer_strategy_code (run_id, layer, strategy, stock_code),
                INDEX idx_run_date (run_date),
                INDEX idx_layer_preset (layer, preset)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='漏斗筛选结果(粗筛+精筛各层)'
        """))

        # screen_result 补充 exchange 列（已存在表需 ALTER）
        try:
            conn.execute(text(
                "ALTER TABLE screen_result ADD COLUMN exchange VARCHAR(10) "
                "COMMENT '交易所' AFTER stock_name"
            ))
            print("  screen_result 新增 exchange 列")
        except Exception:
            pass  # 列已存在

        conn.commit()
    print("✅ 数据库初始化完成: daily_prices, minute_prices, stocks, job_runs, stock_pool, "
          "stock_signal, stock_signal_log, chip_distribution, screen_result")
