# -*- coding: utf-8 -*-
"""
Intelligent Resource Scheduler Module
-------------------------------------
Dynamic workload balancing & co-existence engine for 2 vCPU / 4 GB RAM VPS host:
1. Real-time CPU, RAM, disk I/O, queue depth, and recognition latency telemetry.
2. Recognition Queue priority admission control (low latency priority).
3. Adaptive Upload Queue backpressure & concurrency throttling to prevent CPU thrashing.
4. Automatic recovery and fair resource distribution.
"""

import time
import asyncio
import logging
import psutil
from typing import Dict, Any, Tuple, Optional

from src.pipeline.config import settings

logger = logging.getLogger("pipeline.scheduler")


class IntelligentScheduler:
    def __init__(self):
        self.target_latency_ms = settings.TARGET_RECOGNITION_LATENCY_MS  # 800ms
        self.max_cpu_percent = settings.MAX_CPU_PERCENT  # 85%
        self._active_recognition_jobs = 0
        self._active_upload_jobs = 0
        self._recognition_latencies: list = []
        self._last_balance_time = time.time()
        self._current_upload_throttle = 1.0  # 1.0 = 100% speed, 0.2 = 20% speed

    def register_recognition_start(self):
        self._active_recognition_jobs += 1

    def register_recognition_complete(self, latency_ms: float):
        self._active_recognition_jobs = max(0, self._active_recognition_jobs - 1)
        self._recognition_latencies.append(latency_ms)
        if len(self._recognition_latencies) > 50:
            self._recognition_latencies.pop(0)

        # Trigger dynamic rebalancing after job completion
        self.rebalance_workloads()

    def register_upload_start(self):
        self._active_upload_jobs += 1

    def register_upload_complete(self):
        self._active_upload_jobs = max(0, self._active_upload_jobs - 1)

    def rebalance_workloads(self):
        """
        Dynamically adjusts upload worker concurrency & delay according to CPU usage and latency.
        """
        now = time.time()
        if now - self._last_balance_time < 2.0:
            return

        self._last_balance_time = now
        cpu_usage = psutil.cpu_percent()
        ram_usage = psutil.virtual_memory().percent

        avg_latency = (
            sum(self._recognition_latencies[-10:]) / max(1, len(self._recognition_latencies[-10:]))
            if self._recognition_latencies else 0.0
        )

        # Adaptive throttling rule:
        # If recognition latency > target OR host CPU > 85%, reduce upload concurrency
        if avg_latency > self.target_latency_ms or cpu_usage > self.max_cpu_percent or self._active_recognition_jobs > 2:
            self._current_upload_throttle = max(0.2, self._current_upload_throttle - 0.2)
            logger.info(
                f"Scheduler: High recognition load (latency {round(avg_latency, 1)}ms, CPU {cpu_usage}%). "
                f"Throttling upload concurrency factor to {round(self._current_upload_throttle, 2)}"
            )
        else:
            # Gradually restore upload speed when host load stabilizes
            self._current_upload_throttle = min(1.0, self._current_upload_throttle + 0.1)

    def get_upload_delay_seconds(self) -> float:
        """Returns extra sleep delay for upload workers to maintain recognition latency."""
        return (1.0 - self._current_upload_throttle) * 0.5

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns real-time host resource & queue telemetry."""
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        avg_lat = (
            round(sum(self._recognition_latencies[-20:]) / max(1, len(self._recognition_latencies[-20:])), 1)
            if self._recognition_latencies else 0.0
        )

        return {
            "cpu_percent": cpu,
            "ram_percent": ram,
            "active_recognition_sessions": self._active_recognition_jobs,
            "active_upload_sessions": self._active_upload_jobs,
            "avg_recognition_latency_ms": avg_lat,
            "upload_throttle_factor": round(self._current_upload_throttle, 2),
            "vps_profile": "2 vCPU / 4 GB RAM Hostinger VPS (Optimized)"
        }


intelligent_scheduler = IntelligentScheduler()
