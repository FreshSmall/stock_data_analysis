"""FastAPI 应用 — 股票数据接口 + 前端静态托管"""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import stocks, analyze, jobs, pools

app = FastAPI(title="Stock Data Analysis API", version="0.1.0")

app.include_router(stocks.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(pools.router, prefix="/api")

# 静态托管 web_ui/（必须在 router 之后挂载，避免 /api/* 被静态拦截）
_UI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "web_ui"))
if os.path.isdir(_UI_DIR):
    app.mount("/", StaticFiles(directory=_UI_DIR, html=True), name="ui")
