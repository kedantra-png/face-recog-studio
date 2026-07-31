# -*- coding: utf-8 -*-
"""
Decoupled Background Workers Pool
---------------------------------
Independent asynchronous workers for:
1. UploadWorker: Reassembles chunks, extracts ZIPs, verifies SHA-256 duplicates.
2. EmbeddingWorker: Evaluates image & face quality, crops/aligns faces, computes InsightFace 512-d embeddings, and pushes vectors to Qdrant.
3. DriveWorker: Asynchronously uploads original raw files to Google Drive.
4. HealthWorker: Collects real-time CPU, RAM, Disk space, and queue metrics.
"""

import os
import cv2
import time
import psutil
import asyncio
import logging
import uuid
import numpy as np

from typing import Dict, Any, List
from src.pipeline.config import settings
from src.pipeline.db.mongo import mongo_db
from src.pipeline.db.qdrant_service import qdrant_service
from src.pipeline.storage.disk_storage import disk_storage
from src.pipeline.storage.drive_service import drive_service
from src.pipeline.services.quality_evaluator import quality_evaluator
from src.pipeline.services.face_processor import face_processor
from src.pipeline.queue.background_queue import background_queue, TaskStatus
from src.pipeline.websocket.manager import ws_manager

logger = logging.getLogger("pipeline.workers")


class WorkerPool:
    def __init__(self):
        self.is_running = False
        self.worker_tasks: List[asyncio.Task] = []

    async def start(self):
        """Starts worker pool background tasks."""
        if self.is_running:
            return

        self.is_running = True
        logger.info(f"Starting {settings.NUM_WORKERS} background pipeline workers...")

        # Spawn worker tasks
        self.worker_tasks.append(asyncio.create_task(self._upload_worker_loop()))
        self.worker_tasks.append(asyncio.create_task(self._embedding_worker_loop()))
        self.worker_tasks.append(asyncio.create_task(self._drive_worker_loop()))
        self.worker_tasks.append(asyncio.create_task(self._health_worker_loop()))

    async def stop(self):
        """Gracefully shuts down worker pool tasks."""
        self.is_running = False
        for task in self.worker_tasks:
            task.cancel()
        logger.info("Worker pool background tasks stopped.")

    # ----------------------------------------------------
    # 1. Upload Worker Loop
    # ----------------------------------------------------
    async def _upload_worker_loop(self):
        worker_id = f"upload_worker_{os.getpid()}"
        while self.is_running:
            try:
                task = await background_queue.fetch_next_task("upload_process", worker_id)
                if not task:
                    await asyncio.sleep(1.0)
                    continue

                task_id = task["task_id"]
                job_id = task["job_id"]
                payload = task["payload"]

                logger.info(f"Processing Upload Task: {task_id} for Job: {job_id}")

                # Process single file chunk reassembly OR ZIP extraction
                if payload.get("is_zip"):
                    zip_path = payload["file_path"]
                    extracted_files = disk_storage.extract_zip_safely(zip_path, job_id)

                    for item in extracted_files:
                        sha256_h = item.get("sha256", "")
                        existing_img = await mongo_db.get_image_by_sha256(sha256_h) if sha256_h else None
                        if existing_img:
                            logger.info(f"Duplicate image detected in ZIP (SHA256: {sha256_h}). Skipping backend indexing.")
                            await ws_manager.broadcast("duplicate_skipped", {"job_id": job_id, "filename": item["relative_path"], "sha256": sha256_h})
                        else:
                            await self._enqueue_image_for_embedding(job_id, item["file_path"], item["relative_path"], sha256_h)
                else:
                    file_id = payload["file_id"]
                    total_chunks = payload["total_chunks"]
                    relative_path = payload["relative_path"]

                    out_path, sha256_hash, file_size = await disk_storage.assemble_chunks(
                        job_id, file_id, total_chunks, relative_path
                    )

                    # Security check
                    is_valid, mime_type = disk_storage.validate_security(out_path)
                    if not is_valid:
                        raise ValueError(f"Security check failed: {mime_type}")

                    # Duplicate check
                    existing_image = await mongo_db.get_image_by_sha256(sha256_hash)
                    if existing_image:
                        logger.info(f"Duplicate image detected for SHA256: {sha256_hash}. Skipping redundant embedding & database entry.")
                        await ws_manager.broadcast("duplicate_skipped", {"job_id": job_id, "filename": relative_path, "sha256": sha256_hash})
                    else:
                        await self._enqueue_image_for_embedding(job_id, out_path, relative_path, sha256_hash, mime_type, file_size)

                await background_queue.mark_completed(task_id)
                await ws_manager.broadcast("upload_completed", {"job_id": job_id, "task_id": task_id})


            except Exception as e:
                logger.error(f"Error in UploadWorker: {e}")
                if 'task_id' in locals():
                    await background_queue.mark_failed(task_id, str(e))
                await asyncio.sleep(2.0)

    async def _enqueue_image_for_embedding(
        self, job_id: str, file_path: str, relative_path: str, sha256_hash: str, mime_type: str = "image/jpeg", file_size: int = 0
    ):
        if sha256_hash:
            existing = await mongo_db.get_image_by_sha256(sha256_hash)
            if existing:
                logger.info(f"Duplicate image detected via SHA256 ({sha256_hash}). Skipping backend indexing.")
                return

        image_id = f"img_{uuid.uuid4().hex[:12]}"
        now = time.time()


        image_doc = {
            "image_id": image_id,
            "job_id": job_id,
            "user_id": "default_user",
            "original_filename": os.path.basename(relative_path),
            "internal_filename": os.path.basename(file_path),
            "relative_folder": os.path.dirname(relative_path),
            "file_path": file_path,
            "sha256": sha256_hash,
            "file_size": file_size,
            "mime_type": mime_type,
            "drive_status": "pending",
            "drive_file_id": None,
            "drive_url": None,
            "embedding_status": "queued",
            "detected_faces": 0,
            "quality_score": 0.0,
            "embedding_model": settings.MODEL_NAME,
            "embedding_version": "512_v1",
            "created_at": now,
            "updated_at": now
        }

        await mongo_db.insert_image_metadata(image_doc)

        # Enqueue embedding worker task
        await background_queue.enqueue(
            task_type="generate_embedding",
            payload={"image_id": image_id, "file_path": file_path, "relative_path": relative_path},
            job_id=job_id,
            priority=2
        )

    # ----------------------------------------------------
    # 2. Embedding Worker Loop (InsightFace + Qdrant)
    # ----------------------------------------------------
    async def _embedding_worker_loop(self):
        worker_id = f"embedding_worker_{os.getpid()}"
        while self.is_running:
            try:
                task = await background_queue.fetch_next_task("generate_embedding", worker_id)
                if not task:
                    await asyncio.sleep(1.0)
                    continue

                task_id = task["task_id"]
                job_id = task["job_id"]
                image_id = task["payload"]["image_id"]
                file_path = task["payload"]["file_path"]

                logger.info(f"Generating InsightFace 512-d Embedding for Image: {image_id}")
                await ws_manager.broadcast("embedding_processing", {"job_id": job_id, "image_id": image_id})

                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"Image file missing on disk: {file_path}")

                img = cv2.imread(file_path)
                if img is None:
                    raise ValueError(f"Could not decode image at: {file_path}")

                # Image quality evaluation
                img_quality = quality_evaluator.evaluate_image_quality(img)

                # Run InsightFace face detection (capturing large & small faces) and 5-point alignment
                faces = face_processor.process_image(img)

                faces_stored = []
                qdrant_points = []

                for idx, face in enumerate(faces):
                    # Evaluate face quality
                    face_q = quality_evaluator.evaluate_face_quality(img, face["bbox"], np.array(face["landmarks"]))
                    
                    # Qdrant requires point IDs to be valid UUIDs or integers
                    vector_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{image_id}_face_{idx}"))

                    embedding_vector = face["embedding"]  # 512-d L2 normalized float list

                    payload = {
                        "image_id": image_id,
                        "job_id": job_id,
                        "filename": os.path.basename(file_path),
                        "quality_score": face_q["score"],
                        "confidence": face["confidence"],
                        "created_at": int(time.time())
                    }

                    qdrant_points.append({
                        "id": vector_id,
                        "vector": embedding_vector,
                        "payload": payload
                    })

                    faces_stored.append({
                        "face_index": idx,
                        "bbox": face["bbox"],
                        "confidence": face["confidence"],
                        "quality_score": face_q["score"],
                        "vector_id": vector_id
                    })

                # Batch upsert face vectors to Qdrant
                if qdrant_points:
                    await qdrant_service.batch_upsert_embeddings(qdrant_points)

                # Update MongoDB Image Metadata
                await mongo_db.update_image_metadata(
                    image_id,
                    {
                        "embedding_status": "completed",
                        "detected_faces": len(faces_stored),
                        "quality_score": img_quality["score"],
                        "faces_detail": faces_stored,
                        "updated_at": time.time()
                    }
                )

                # Enqueue Google Drive background upload task
                await background_queue.enqueue(
                    task_type="upload_drive",
                    payload={"image_id": image_id, "file_path": file_path, "filename": os.path.basename(file_path)},
                    job_id=job_id,
                    priority=3
                )

                await background_queue.mark_completed(task_id)
                await ws_manager.broadcast("embedding_completed", {
                    "job_id": job_id,
                    "image_id": image_id,
                    "detected_faces": len(faces_stored),
                    "quality_score": img_quality["score"]
                })

            except Exception as e:
                logger.error(f"Error in EmbeddingWorker: {e}")
                if 'task_id' in locals():
                    await background_queue.mark_failed(task_id, str(e))
                await asyncio.sleep(2.0)

    # ----------------------------------------------------
    # 3. Google Drive Worker Loop
    # ----------------------------------------------------
    async def _drive_worker_loop(self):
        worker_id = f"drive_worker_{os.getpid()}"
        while self.is_running:
            try:
                task = await background_queue.fetch_next_task("upload_drive", worker_id)
                if not task:
                    await asyncio.sleep(2.0)
                    continue

                task_id = task["task_id"]
                job_id = task["job_id"]
                image_id = task["payload"]["image_id"]
                file_path = task["payload"]["file_path"]
                filename = task["payload"]["filename"]

                logger.info(f"Uploading raw uncompressed image to Google Drive: {filename}")

                drive_res = await drive_service.upload_file(file_path, filename)
                if drive_res:
                    await mongo_db.update_image_metadata(
                        image_id,
                        {
                            "drive_status": "completed",
                            "drive_file_id": drive_res.get("drive_file_id"),
                            "drive_url": drive_res.get("drive_url"),
                            "updated_at": time.time()
                        }
                    )
                    await ws_manager.broadcast("drive_completed", {
                        "job_id": job_id,
                        "image_id": image_id,
                        "drive_url": drive_res.get("drive_url")
                    })

                await background_queue.mark_completed(task_id)

            except Exception as e:
                logger.error(f"Error in DriveWorker: {e}")
                if 'task_id' in locals():
                    await background_queue.mark_failed(task_id, str(e))
                await asyncio.sleep(3.0)

    # ----------------------------------------------------
    # 4. System Health & Telemetry Worker Loop
    # ----------------------------------------------------
    async def _health_worker_loop(self):
        while self.is_running:
            try:
                cpu_percent = psutil.cpu_percent()
                memory_info = psutil.virtual_memory()
                disk_info = psutil.disk_usage("/")
                queue_metrics = await background_queue.get_queue_metrics()

                health_data = {
                    "cpu_percent": cpu_percent,
                    "ram_percent": memory_info.percent,
                    "ram_used_mb": round(memory_info.used / (1024 * 1024), 1),
                    "disk_free_gb": round(disk_info.free / (1024 * 1024 * 1024), 2),
                    "queue": queue_metrics,
                    "timestamp": time.time()
                }

                await ws_manager.broadcast("system_metrics", health_data)
                await asyncio.sleep(5.0)  # Telemetry broadcast every 5 seconds
            except Exception as e:
                logger.warning(f"HealthWorker telemetry exception: {e}")
                await asyncio.sleep(5.0)


worker_pool = WorkerPool()
