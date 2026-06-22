"""
APScheduler 调度器 — 注册定时任务
"""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import JOB_DAILY_CRON, JOB_MINUTE_CRON, POOL_CRON, SIGNAL_CRON, FUNNEL_CRON, RECOMMEND_CRON

from .jobs import job_fetch_daily, job_fetch_minute, job_pool, job_signal, job_funnel, job_recommend


def build_scheduler() -> BlockingScheduler:
    """构建并返回调度器（未启动）"""
    sched = BlockingScheduler(timezone="Asia/Shanghai")
    sched.add_job(job_fetch_daily, CronTrigger.from_crontab(JOB_DAILY_CRON),
                  id="job_fetch_daily", misfire_grace_time=3600)
    sched.add_job(job_fetch_minute, CronTrigger.from_crontab(JOB_MINUTE_CRON),
                  id="job_fetch_minute", misfire_grace_time=3600)
    sched.add_job(job_pool, CronTrigger.from_crontab(POOL_CRON),
                  id="job_pool", misfire_grace_time=3600)
    sched.add_job(job_signal, CronTrigger.from_crontab(SIGNAL_CRON),
                  id="job_signal", misfire_grace_time=3600)
    sched.add_job(job_funnel, CronTrigger.from_crontab(FUNNEL_CRON),
                  id="job_funnel", misfire_grace_time=3600)
    sched.add_job(job_recommend, CronTrigger.from_crontab(RECOMMEND_CRON),
                  id="job_recommend", misfire_grace_time=3600)
    return sched
