# -*- coding: utf-8 -*-
"""
AI Model Lifecycle & Dynamic RAM Manager
-----------------------------------------
Manages memory mounting/unmounting for InsightFace ONNX models & Landmark Liveness Service:
1. Warmup & Pre-loading: Pre-loads AI models into RAM during server startup.
2. Sub-Millisecond Activity Reset: Every incoming request calls touch_activity() taking < 0.01ms,
   resetting the 3h 30m idle timer.
3. Automatic Dynamic RAM Unmounting: If no requests are received for > 3.30 hours (12,600s),
   the models are automatically unmounted from RAM and garbage collected to free system memory.
4. Auto-Reload on Request: If a request arrives while unmounted, models are immediately reloaded back into RAM.
5. Master Admin Control: Provides FastAPI endpoints to inspect telemetry, dynamically adjust idle timeout,
   toggle 'never_unmount' mode, or manually trigger load/unload.
"""

import os
import sys
import gc
import time
import asyncio
import logging
from typing import Dict, Any, Optional

from src.pipeline.services.anti_spoof_service import anti_spoof_service
from src.pipeline.services.embedding_service import embedding_service
from src.pipeline.services.face_processor import face_processor

logger = logging.getLogger("pipeline.model_lifecycle")


class ModelLifecycleManager:
    """
    Manages the RAM mounting, auto-unmounting, and on-demand reloading of PyTorch & ONNX AI models.
    """

    def __init__(self):
        # Default idle timeout: 3 hours 30 minutes = 210 minutes = 12,600 seconds
        self.idle_timeout_seconds: float = 12600.0
        self.never_unmount: bool = False
        self.last_request_time: float = time.time()
        self.is_models_loaded: bool = False
        self._watchdog_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def touch_activity(self) -> None:
        """
        Sub-millisecond fast execution (< 0.01ms) to reset the idle timer on every incoming request.
        If models were unmounted due to prolonged inactivity, triggers automatic on-demand reloading.
        """
        self.last_request_time = time.time()
        if not self.is_models_loaded:
            # Auto-reload models if unmounted
            self.load_all_models()

    def load_all_models(self) -> Dict[str, Any]:
        """
        Loads and warms up Landmark Liveness Engine and InsightFace ONNX runtime sessions into RAM.
        """
        start_time = time.time()
        logger.info("Mounting AI models (Landmark Liveness + InsightFace ArcFace/SCRFD) into system RAM...")

        try:
            # 1. Init & Warmup InsightFace Embedding & Detection Engine
            embedding_service.warmup()
            anti_spoof_service.warmup()

            self.is_models_loaded = True
            self.last_request_time = time.time()
            cost_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(f"InsightFace ONNX AI Models successfully mounted in RAM in {cost_ms}ms. Idle timeout reset to 3h 30m.")
            return {
                "success": True,
                "is_models_loaded": True,
                "latency_ms": cost_ms,
                "message": f"Models mounted in RAM in {cost_ms}ms"
            }

        except Exception as e:
            logger.error(f"Error mounting AI models into RAM: {e}")
            return {
                "success": False,
                "is_models_loaded": False,
                "error": str(e)
            }

    def unload_all_models(self) -> Dict[str, Any]:
        """
        Unmounts AI models from RAM, releases ONNX runtime sessions & PyTorch tensors,
        and executes garbage collection to free system memory.
        """
        start_time = time.time()
        logger.info("Unmounting AI models from RAM due to inactivity / administrative request...")

        try:
            # Unload InsightFace FaceProcessor ONNX sessions
            if hasattr(face_processor, "app") and face_processor.app is not None:
                face_processor.app = None
            face_processor._initialized = False

            # 3. Clear PyTorch CUDA cache if available and invoke garbage collection
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

            gc.collect()

            self.is_models_loaded = False
            cost_ms = round((time.time() - start_time) * 1000, 2)

            logger.info(f"AI Models successfully unmounted from RAM in {cost_ms}ms. System RAM freed.")
            return {
                "success": True,
                "is_models_loaded": False,
                "latency_ms": cost_ms,
                "message": f"Models unmounted from RAM in {cost_ms}ms"
            }

        except Exception as e:
            logger.error(f"Error unmounting AI models from RAM: {e}")
            return {
                "success": False,
                "is_models_loaded": self.is_models_loaded,
                "error": str(e)
            }

    def start_idle_watchdog(self) -> None:
        """Launches background asyncio task checking for 3h 30m idle inactivity."""
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._idle_watchdog_loop())
            logger.info("Model lifecycle idle watchdog loop initialized.")

    async def _idle_watchdog_loop(self) -> None:
        """Background loop checking idle time every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                if self.never_unmount:
                    continue

                if self.is_models_loaded:
                    idle_seconds = time.time() - self.last_request_time
                    if idle_seconds >= self.idle_timeout_seconds:
                        hours = round(idle_seconds / 3600.0, 2)
                        logger.warning(
                            f"System inactive for {hours} hours (>= {round(self.idle_timeout_seconds / 3600.0, 2)}h threshold). "
                            "Unmounting AI models from RAM..."
                        )
                        self.unload_all_models()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in model lifecycle watchdog loop: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns current model RAM telemetry status, idle time, and configuration."""
        now = time.time()
        idle_seconds = round(now - self.last_request_time, 1) if self.is_models_loaded else 0.0

        return {
            "is_models_loaded": self.is_models_loaded,
            "never_unmount": self.never_unmount,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "idle_timeout_hours": round(self.idle_timeout_seconds / 3600.0, 2),
            "idle_seconds": idle_seconds,
            "last_request_timestamp": self.last_request_time,
            "liveness_service_loaded": anti_spoof_service.is_loaded,
            "minifasnet_loaded": anti_spoof_service.is_loaded,
            "insightface_loaded": face_processor._initialized and face_processor.app is not None
        }

    def set_config(
        self,
        idle_timeout_seconds: Optional[float] = None,
        never_unmount: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Updates idle timeout duration and never_unmount setting dynamically."""
        if idle_timeout_seconds is not None and idle_timeout_seconds > 0:
            self.idle_timeout_seconds = float(idle_timeout_seconds)

        if never_unmount is not None:
            self.never_unmount = bool(never_unmount)

        logger.info(
            f"Updated Model Lifecycle Config: idle_timeout={round(self.idle_timeout_seconds/3600.0, 2)}h, "
            f"never_unmount={self.never_unmount}"
        )
        return self.get_status()


model_lifecycle_manager = ModelLifecycleManager()
