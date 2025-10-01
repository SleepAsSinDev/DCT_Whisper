# backend/usage_store.py
"""
Usage store (in-memory, thread-safe) สำหรับนับโควตา/งาน
- นาทีต่อวัน/เดือน (minutes_today / minutes_month)
- reservation -> commit / rollback
- running jobs ต่อ user/tenant
หมายเหตุ: โปรดเปลี่ยนเป็นฐานข้อมูลจริง (Postgres/Redis) เมื่อขึ้นโปรดักชัน
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, Tuple
import math


def _day_key() -> str:
    # ใช้ UTC ให้สอดคล้องกันทุกอินสแตนซ์
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m")


@dataclass
class UserCounters:
    minutes_today: int = 0
    minutes_month: int = 0
    reserved_minutes: int = 0
    running_jobs: int = 0


class UsageStore:
    """
    โครงสร้างข้อมูล:
      - per (tenant_id, user_id, day)   -> minutes_today
      - per (tenant_id, user_id, month) -> minutes_month
      - per (tenant_id, user_id)        -> UserCounters (รวม reserved & running_jobs)
      - per tenant_id                   -> running_jobs_tenant
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._per_user_day: Dict[Tuple[str, str, str], int] = {}
        self._per_user_month: Dict[Tuple[str, str, str], int] = {}
        self._user_counters: Dict[Tuple[str, str], UserCounters] = {}
        self._running_jobs_tenant: Dict[str, int] = {}

    # ---------- helpers ----------
    def _uc(self, tenant_id: str, user_id: str) -> UserCounters:
        key = (tenant_id, user_id)
        if key not in self._user_counters:
            self._user_counters[key] = UserCounters()
        return self._user_counters[key]

    def _get_today(self, tenant_id: str, user_id: str) -> int:
        return self._per_user_day.get((tenant_id, user_id, _day_key()), 0)

    def _get_month(self, tenant_id: str, user_id: str) -> int:
        return self._per_user_month.get((tenant_id, user_id, _month_key()), 0)

    # ---------- public API ----------
    def snapshot(self, tenant_id: str, user_id: str) -> Dict[str, int]:
        with self._lock:
            uc = self._uc(tenant_id, user_id)
            return {
                "minutes_today": self._get_today(tenant_id, user_id),
                "minutes_month": self._get_month(tenant_id, user_id),
                "reserved_minutes": uc.reserved_minutes,
                "running_jobs_user": uc.running_jobs,
                "running_jobs_tenant": self._running_jobs_tenant.get(tenant_id, 0),
            }

    def can_consume_minutes(
        self,
        tenant_id: str,
        user_id: str,
        estimate_minutes: int,
        limits: Dict[str, int],
    ) -> bool:
        """
        ตรวจว่านับรวม reserved แล้ว จะเกิน minutes_per_day / minutes_per_month หรือไม่
        """
        est = max(1, int(math.ceil(estimate_minutes)))
        with self._lock:
            uc = self._uc(tenant_id, user_id)
            minutes_today = self._get_today(tenant_id, user_id)
            minutes_month = self._get_month(tenant_id, user_id)

            if minutes_today + uc.reserved_minutes + est > limits["minutes_per_day"]:
                return False
            if minutes_month + uc.reserved_minutes + est > limits["minutes_per_month"]:
                return False
            return True

    def reserve_minutes(self, tenant_id: str, user_id: str, estimate_minutes: int) -> None:
        """
        กันนาทีไว้ชั่วคราวก่อนส่งงานจริง
        """
        est = max(1, int(math.ceil(estimate_minutes)))
        with self._lock:
            uc = self._uc(tenant_id, user_id)
            uc.reserved_minutes += est

    def rollback_minutes(self, tenant_id: str, user_id: str, estimate_minutes: int) -> None:
        """
        ยกเลิกการกันนาที (เมื่อ job submit ล้มเหลว)
        """
        est = max(1, int(math.ceil(estimate_minutes)))
        with self._lock:
            uc = self._uc(tenant_id, user_id)
            uc.reserved_minutes = max(0, uc.reserved_minutes - est)

    def commit_minutes(self, tenant_id: str, user_id: str, actual_minutes: int) -> None:
        """
        ยืนยันการใช้นาทีจริง (เมื่องานเสร็จ)
        - ตัด reserved ออก (เท่าที่กันไว้)
        - เติมลง counters วัน/เดือน
        """
        amt = max(1, int(math.ceil(actual_minutes)))
        dayk = (tenant_id, user_id, _day_key())
        monthk = (tenant_id, user_id, _month_key())
        with self._lock:
            self._per_user_day[dayk] = self._per_user_day.get(dayk, 0) + amt
            self._per_user_month[monthk] = self._per_user_month.get(monthk, 0) + amt

            uc = self._uc(tenant_id, user_id)
            # ตัด reserved ตามจริง แต่อย่าติดลบ
            uc.reserved_minutes = max(0, uc.reserved_minutes - amt)

    # ---------- running jobs ----------
    def inc_running(self, tenant_id: str, user_id: str) -> None:
        with self._lock:
            uc = self._uc(tenant_id, user_id)
            uc.running_jobs += 1
            self._running_jobs_tenant[tenant_id] = self._running_jobs_tenant.get(tenant_id, 0) + 1

    def dec_running(self, tenant_id: str, user_id: str) -> None:
        with self._lock:
            uc = self._uc(tenant_id, user_id)
            uc.running_jobs = max(0, uc.running_jobs - 1)
            self._running_jobs_tenant[tenant_id] = max(0, self._running_jobs_tenant.get(tenant_id, 0) - 1)

    def running_user(self, tenant_id: str, user_id: str) -> int:
        with self._lock:
            return self._uc(tenant_id, user_id).running_jobs

    def running_tenant(self, tenant_id: str) -> int:
        with self._lock:
            return self._running_jobs_tenant.get(tenant_id, 0)


# สร้างอินสแตนซ์เดียวให้ main.py import ไปใช้
usage_store = UsageStore()
