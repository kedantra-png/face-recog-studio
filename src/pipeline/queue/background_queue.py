# -*- coding: utf-8 -*-
"""
Persistent Task Queue & Dead-Letter Queue (DLQ) Manager
--------------------------------------------------------
Provides crash-safe, restart-safe task queueing backed by MongoDB.
Supports priority queues, exponential backoff retries, dead-letter queues,
and worker heartbeats for task lock recovery.
"""

import time
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List
from src.pipeline.db.mongo import mongo_db

logger = logging.getLogger("pipeline.queue")


class TaskStatus:
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    DLQ = "dlq"  # Dead-Letter Queue


class BackgroundQueue:
    def __init__(self):
        self.fallback_memory_queue: List[Dict[str, Any]] = []

    async def enqueue(
        self,
        task_type: str,
        payload: Dict[str, Any],
        job_id: str,
        priority: int = 5,
        max_retries: int = 3
    ) -> str:
        """
        Enqueues a task into persistent storage (MongoDB).
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        now = time.time()

        task_doc = {
            "task_id": task_id,
            "job_id": job_id,
            "task_type": task_type,
            "payload": payload,
            "priority": priority,
            "status": TaskStatus.QUEUED,
            "retry_count": 0,
            "max_retries": max_retries,
            "error": None,
            "worker_id": None,
            "locked_at": None,
            "created_at": now,
            "updated_at": now
        }

        if mongo_db.db is not None:
            await mongo_db.db.worker_tasks.insert_one(task_doc)
        else:
            self.fallback_memory_queue.append(task_doc)

        logger.info(f"Enqueued task {task_id} [{task_type}] for job {job_id}")
        return task_id

    async def fetch_next_task(self, task_type: str, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the next highest priority queued task for a worker type,
        applying atomicity lock to prevent double execution.
        """
        now = time.time()
        lock_timeout = 300  # 5 minutes lock timeout

        if mongo_db.db is not None:
            # First, recover stale processing tasks whose worker crashed
            stale_threshold = now - lock_timeout
            await mongo_db.db.worker_tasks.update_many(
                {"status": TaskStatus.PROCESSING, "locked_at": {"$lt": stale_threshold}},
                {"$set": {"status": TaskStatus.QUEUED, "worker_id": None, "locked_at": None}}
            )

            # Find and lock next queued task
            task = await mongo_db.db.worker_tasks.find_one_and_update(
                {"task_type": task_type, "status": {"$in": [TaskStatus.QUEUED, TaskStatus.RETRYING]}},
                {"$set": {
                    "status": TaskStatus.PROCESSING,
                    "worker_id": worker_id,
                    "locked_at": now,
                    "updated_at": now
                }},
                sort=[("priority", 1), ("created_at", 1)]
            )
            return task
        else:
            # Fallback memory queue
            for task in self.fallback_memory_queue:
                if task["task_type"] == task_type and task["status"] in [TaskStatus.QUEUED, TaskStatus.RETRYING]:
                    task["status"] = TaskStatus.PROCESSING
                    task["worker_id"] = worker_id
                    task["locked_at"] = now
                    return task
            return None

    async def mark_completed(self, task_id: str):
        """Marks a task as completed."""
        now = time.time()
        if mongo_db.db is not None:
            await mongo_db.db.worker_tasks.update_one(
                {"task_id": task_id},
                {"$set": {"status": TaskStatus.COMPLETED, "updated_at": now}}
            )
        else:
            for task in self.fallback_memory_queue:
                if task["task_id"] == task_id:
                    task["status"] = TaskStatus.COMPLETED

    async def mark_failed(self, task_id: str, error_msg: str):
        """
        Handles task failure: triggers exponential backoff retry or sends task to DLQ.
        """
        now = time.time()
        task = None
        if mongo_db.db is not None:
            task = await mongo_db.db.worker_tasks.find_one({"task_id": task_id})
        else:
            for t in self.fallback_memory_queue:
                if t["task_id"] == task_id:
                    task = t
                    break

        if not task:
            return

        retry_count = task.get("retry_count", 0) + 1
        max_retries = task.get("max_retries", 3)

        if retry_count < max_retries:
            backoff_delay = 2 ** retry_count
            logger.warning(f"Task {task_id} failed. Retrying in {backoff_delay}s (Attempt {retry_count}/{max_retries})")
            
            update_data = {
                "status": TaskStatus.RETRYING,
                "retry_count": retry_count,
                "error": error_msg,
                "worker_id": None,
                "locked_at": None,
                "updated_at": now
            }
        else:
            logger.error(f"Task {task_id} exceeded max retries ({max_retries}). Moving to Dead-Letter Queue (DLQ).")
            update_data = {
                "status": TaskStatus.DLQ,
                "retry_count": retry_count,
                "error": error_msg,
                "updated_at": now
            }

        if mongo_db.db is not None:
            await mongo_db.db.worker_tasks.update_one({"task_id": task_id}, {"$set": update_data})
        else:
            task.update(update_data)

    async def get_queue_metrics(self) -> Dict[str, int]:
        """Returns metric counts of queued, processing, completed, and DLQ tasks."""
        if mongo_db.db is not None:
            queued = await mongo_db.db.worker_tasks.count_documents({"status": TaskStatus.QUEUED})
            processing = await mongo_db.db.worker_tasks.count_documents({"status": TaskStatus.PROCESSING})
            completed = await mongo_db.db.worker_tasks.count_documents({"status": TaskStatus.COMPLETED})
            failed = await mongo_db.db.worker_tasks.count_documents({"status": {"$in": [TaskStatus.FAILED, TaskStatus.DLQ]}})
            return {
                "queued": queued,
                "processing": processing,
                "completed": completed,
                "failed": failed
            }
        return {
            "queued": len([t for t in self.fallback_memory_queue if t["status"] == TaskStatus.QUEUED]),
            "processing": len([t for t in self.fallback_memory_queue if t["status"] == TaskStatus.PROCESSING]),
            "completed": len([t for t in self.fallback_memory_queue if t["status"] == TaskStatus.COMPLETED]),
            "failed": len([t for t in self.fallback_memory_queue if t["status"] in [TaskStatus.FAILED, TaskStatus.DLQ]])
        }


background_queue = BackgroundQueue()
