"""
数据写入 — 批量 upsert + 任务执行记录
"""
from typing import Optional

from sqlalchemy import text

from .connection import get_engine


def upsert_rows(rows: list[dict], table: str, conflict_cols: list[str]):
    """
    通用批量 upsert
    rows:        要写入的字典列表
    table:       表名
    conflict_cols: 唯一键列名（不参与 UPDATE）
    """
    if not rows:
        return 0
    engine = get_engine()
    cols = list(rows[0].keys())
    col_str = ", ".join(f"`{c}`" for c in cols)
    val_str = ", ".join(f":{c}" for c in cols)
    update_cols = [c for c in cols if c not in conflict_cols]
    update_str = ", ".join(f"`{c}`=VALUES(`{c}`)" for c in update_cols)

    sql = text(
        f"INSERT INTO {table} ({col_str}) VALUES ({val_str}) "
        f"ON DUPLICATE KEY UPDATE {update_str}"
    )
    with engine.begin() as conn:
        conn.execute(sql, rows)
    return len(rows)


def start_job_run(job_name: str) -> int:
    """记录任务开始（status=running），返回 run_id"""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text(
            "INSERT INTO job_runs (job_name, started_at, status) "
            "VALUES (:name, NOW(), 'running')"
        ), {"name": job_name})
        return result.lastrowid


def finish_job_run(run_id: int, status: str,
                   rows: Optional[int] = None, error: Optional[str] = None):
    """更新任务结束状态"""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE job_runs SET finished_at=NOW(), status=:status, "
            "rows_affected=:rows, error=:error WHERE id=:id"
        ), {"id": run_id, "status": status, "rows": rows, "error": error})
