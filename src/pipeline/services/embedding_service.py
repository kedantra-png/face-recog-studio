# -*- coding: utf-8 -*-
"""
Embedding Service Module
------------------------
InsightFace 512-Dimensional Face Feature Extractor:
1. Warmup and persistent model loading (InsightFace buffalo_l with CPU Execution Provider).
2. Computes 512-d embeddings on aligned face images.
3. L2 vector normalization.
"""

import time
import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Tuple, Optional

from src.pipeline.config import settings
from src.pipeline.services.face_processor import face_processor

logger = logging.getLogger("pipeline.embedding")


class EmbeddingService:
    def __init__(self):
        self.processor = face_processor
        self.dimension = settings.EMBEDDING_DIMENSION  # 512

    def warmup(self):
        """Warms up ONNX runtime sessions by running a dummy 112x112 image."""
        try:
            logger.info("Warming up InsightFace embedding engine...")
            dummy_img = np.zeros((112, 112, 3), dtype=np.uint8)
            cv2.rectangle(dummy_img, (30, 30), (80, 80), (255, 255, 255), -1)
            _ = self.extract_embedding(dummy_img)
            logger.info("InsightFace embedding engine warmed up successfully.")
        except Exception as e:
            logger.warning(f"Embedding engine warmup warning: {e}")

    def extract_embedding(self, img: np.ndarray) -> Dict[str, Any]:
        """
        Detects face, aligns landmarks, and extracts 512-d L2 normalized embedding vector.
        Returns:
            - success: bool
            - embedding: List[float] (512-d)
            - confidence: float
            - bbox: List[int]
            - landmarks: List[List[float]]
            - latency_ms: float
            - error: Optional[str]
        """
        start_time = time.time()
        if img is None or img.size == 0:
            return {
                "success": False,
                "embedding": [],
                "confidence": 0.0,
                "bbox": [0, 0, 0, 0],
                "landmarks": [],
                "latency_ms": 0.0,
                "error": "Empty image frame"
            }

        try:
            faces = self.processor.process_image(img)
            cost_ms = round((time.time() - start_time) * 1000, 2)

            if not faces:
                return {
                    "success": False,
                    "embedding": [],
                    "confidence": 0.0,
                    "bbox": [0, 0, 0, 0],
                    "landmarks": [],
                    "latency_ms": cost_ms,
                    "error": "No valid face detected for embedding extraction"
                }

            # Select face with highest detection confidence
            best_face = max(faces, key=lambda f: f.get("confidence", 0.0))
            embedding = best_face.get("embedding", [])

            if len(embedding) != self.dimension:
                return {
                    "success": False,
                    "embedding": [],
                    "confidence": 0.0,
                    "bbox": best_face.get("bbox", [0, 0, 0, 0]),
                    "landmarks": best_face.get("landmarks", []),
                    "latency_ms": cost_ms,
                    "error": f"Invalid embedding dimension ({len(embedding)} vs expected {self.dimension})"
                }

            return {
                "success": True,
                "embedding": embedding,
                "confidence": best_face.get("confidence", 0.0),
                "bbox": best_face.get("bbox", [0, 0, 0, 0]),
                "landmarks": best_face.get("landmarks", []),
                "aligned_crop": best_face.get("aligned_crop"),
                "latency_ms": cost_ms,
                "error": None
            }

        except Exception as e:
            logger.error(f"Error during face embedding extraction: {e}")
            return {
                "success": False,
                "embedding": [],
                "confidence": 0.0,
                "bbox": [0, 0, 0, 0],
                "landmarks": [],
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "error": str(e)
            }


embedding_service = EmbeddingService()
