"""Track usage reservations and quotas in-memory (with optional SQLite hooks)."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple


@dataclass
class UsageJob:
    user_id: str
    tenant_id: str
    reserved_minutes: int
    task_id: str


@dataclass
class UsageRecord:
    day: date
    month: Tuple[int, int]
    minutes_today: int = 0
    minutes_month: int = 0
    reserved_minutes: int = 0
    active_jobs: int = 0


class UsageStore:
    """Usage accounting helper implementing reservation/commit logic."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._user_records: Dict[str, UsageRecord] = {}
        self._tenant_records: Dict[str, UsageRecord] = {}
        self._jobs: Dict[str, UsageJob] = {}

    async def reserve(
        self,
        user_id: str,
        tenant_id: str,
        minutes: int,
        job_id: str,
        limits: dict,
    ) -> None:
        async with self._lock:
            self._ensure_records(user_id, tenant_id)
            user = self._user_records[user_id]
            tenant = self._tenant_records[tenant_id]

            if user.active_jobs >= limits["concurrent_user"]:
                raise RuntimeError("concurrency_user")
            if tenant.active_jobs >= limits["concurrent_tenant"]:
                raise RuntimeError("concurrency_tenant")


            day_limit = limits.get("minutes_per_day", 0)
            if day_limit > 0 and user.minutes_today + user.reserved_minutes + minutes > day_limit:
                raise RuntimeError("quota_day")
            month_limit = limits.get("minutes_per_month", 0)
            if month_limit > 0 and user.minutes_month + user.reserved_minutes + minutes > month_limit:

            if user.minutes_today + user.reserved_minutes + minutes > limits["minutes_per_day"]:
                raise RuntimeError("quota_day")
            if user.minutes_month + user.reserved_minutes + minutes > limits["minutes_per_month"]:

                raise RuntimeError("quota_month")

            user.reserved_minutes += minutes
            user.active_jobs += 1
            tenant.reserved_minutes += minutes
            tenant.active_jobs += 1
            self._jobs[job_id] = UsageJob(user_id, tenant_id, minutes, task_id=job_id)

    async def confirm(self, reservation_id: str, task_id: str) -> None:
        async with self._lock:
            job = self._jobs.pop(reservation_id, None)
            if not job:
                raise RuntimeError("reservation_missing")
            job.task_id = task_id
            self._jobs[task_id] = job

    async def commit(self, task_id: str, minutes_actual: int) -> None:
        async with self._lock:
            job = self._jobs.pop(task_id, None)
            if not job:
                return
            user = self._user_records[job.user_id]
            tenant = self._tenant_records[job.tenant_id]
            self._apply_period_rollover(user)
            self._apply_period_rollover(tenant)

            reserved = job.reserved_minutes
            user.reserved_minutes = max(0, user.reserved_minutes - reserved)
            tenant.reserved_minutes = max(0, tenant.reserved_minutes - reserved)
            user.active_jobs = max(0, user.active_jobs - 1)
            tenant.active_jobs = max(0, tenant.active_jobs - 1)
            user.minutes_today += minutes_actual
            tenant.minutes_today += minutes_actual
            user.minutes_month += minutes_actual
            tenant.minutes_month += minutes_actual

    async def rollback(self, job_id: str) -> None:
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if not job:
                return
            user = self._user_records[job.user_id]
            tenant = self._tenant_records[job.tenant_id]
            self._apply_period_rollover(user)
            self._apply_period_rollover(tenant)
            reserved = job.reserved_minutes
            user.reserved_minutes = max(0, user.reserved_minutes - reserved)
            tenant.reserved_minutes = max(0, tenant.reserved_minutes - reserved)
            user.active_jobs = max(0, user.active_jobs - 1)
            tenant.active_jobs = max(0, tenant.active_jobs - 1)

    async def get_usage(self, user_id: str, tenant_id: str) -> dict:
        async with self._lock:
            self._ensure_records(user_id, tenant_id)
            user = self._user_records[user_id]
            tenant = self._tenant_records[tenant_id]
            return {
                "user": {
                    "minutes_today": user.minutes_today,
                    "minutes_month": user.minutes_month,
                    "reserved_minutes": user.reserved_minutes,
                    "active_jobs": user.active_jobs,
                },
                "tenant": {
                    "minutes_today": tenant.minutes_today,
                    "minutes_month": tenant.minutes_month,
                    "reserved_minutes": tenant.reserved_minutes,
                    "active_jobs": tenant.active_jobs,
                },
            }

    def _ensure_records(self, user_id: str, tenant_id: str) -> None:
        if user_id not in self._user_records:
            self._user_records[user_id] = UsageRecord(day=date.today(), month=(date.today().year, date.today().month))
        if tenant_id not in self._tenant_records:
            self._tenant_records[tenant_id] = UsageRecord(day=date.today(), month=(date.today().year, date.today().month))
        self._apply_period_rollover(self._user_records[user_id])
        self._apply_period_rollover(self._tenant_records[tenant_id])

    def _apply_period_rollover(self, record: UsageRecord) -> None:
        today = date.today()
        if record.day != today:
            record.day = today
            record.minutes_today = 0
            record.reserved_minutes = 0
        current_month = (today.year, today.month)
        if record.month != current_month:
            record.month = current_month
            record.minutes_month = 0


usage_store = UsageStore()
