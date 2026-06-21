"""
数据库连接管理
"""
from sqlalchemy import create_engine

from config import DB_URL


def get_engine():
    return create_engine(DB_URL, pool_pre_ping=True, pool_recycle=3600)
