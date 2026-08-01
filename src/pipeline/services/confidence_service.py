# -*- coding: utf-8 -*-
"""
Confidence & Re-Ranking Service Module
----------------------------------------
Computes final recognition confidence by re-ranking Qdrant candidate matches using:
1. Cosine similarity score
2. Face quality score
3. Anti-spoof confidence
4. Multi-frame candidate consistency boost
5. MongoDB person metadata lookup
"""

import os
import base64
import cv2
import logging
from typing import List, Dict, Any, Tuple, Optional
from src.pipeline.config import settings
from src.pipeline.db.mongo import mongo_db

logger = logging.getLogger("pipeline.confidence")


def resolve_image_thumbnail(file_path: str) -> str:
    """Converts a local image file path or Google Drive link into a self-contained base64 JPEG URI or Drive thumbnail URL."""
    if not file_path:
        return ""

    if file_path.startswith("data:image/"):
        return file_path

    # Convert Google Drive view URLs to direct 100% full-resolution CDN links (s0 = full original quality)
    if "drive.google.com" in file_path:
        if "/file/d/" in file_path:
            drive_id = file_path.split("/file/d/")[1].split("/")[0]
            return f"https://lh3.googleusercontent.com/d/{drive_id}=s0"
        elif "id=" in file_path:
            drive_id = file_path.split("id=")[1].split("&")[0]
            return f"https://lh3.googleusercontent.com/d/{drive_id}=s0"
        return file_path

    if file_path.startswith("http://") or file_path.startswith("https://"):
        return file_path

    clean_path = file_path.replace("\\", "/")
    possible_paths = [
        clean_path,
        os.path.join(os.getcwd(), clean_path),
        os.path.join(getattr(settings, 'UPLOAD_DIR', 'temp_uploads'), os.path.basename(clean_path))
    ]

    for path in possible_paths:
        if os.path.exists(path) and os.path.isfile(path):
            try:
                img = cv2.imread(path)
                if img is not None:
                    # High quality 98% JPEG encoding without downscaling loss
                    _, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 98])
                    return f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
            except Exception as e:
                logger.warning(f"Error encoding thumbnail image at {path}: {e}")


    return f"http://127.0.0.1:8000/{clean_path.lstrip('/')}"



class ConfidenceService:
    def __init__(self):
        self.similarity_threshold = settings.RECOGNITION_SIMILARITY_THRESHOLD

    async def calculate_recognition_confidence(
        self,
        qdrant_candidates: List[Dict[str, Any]],
        face_quality_score: float,
        anti_spoof_confidence: float,
        detection_confidence: float,
        multi_frame_consensus: float = 1.0
    ) -> Dict[str, Any]:
        """
        Re-ranks vector search candidates and computes overall recognition confidence score.
        """
        if not qdrant_candidates:
            return {
                "match_found": False,
                "person_id": None,
                "person_metadata": None,
                "similarity_score": 0.0,
                "overall_confidence": 0.0,
                "top_matches": [],
                "recognition_status": "NO_MATCH"
            }

        re_ranked_matches = []
        best_match = None
        highest_confidence = 0.0

        for cand in qdrant_candidates:
            raw_sim = cand.get("score", 0.0)
            payload = cand.get("payload", {})

            # Formula for multi-factor confidence re-ranking:
            # 50% Cosine Similarity + 20% Quality + 15% Anti-Spoof + 15% Detection Score
            weighted_conf = (
                0.50 * raw_sim +
                0.20 * face_quality_score +
                0.15 * anti_spoof_confidence +
                0.15 * detection_confidence
            )

            # Apply consensus boost if multiple frames matched the same vector point
            weighted_conf = min(1.0, weighted_conf * multi_frame_consensus)

            image_id = payload.get("image_id") or cand.get("id")
            person_id = payload.get("person_id") or payload.get("folder_name") or f"PERSON_{image_id[:8]}"

            # Fetch metadata from MongoDB
            mongo_meta = await self._fetch_person_metadata(image_id, person_id)
            raw_thumb = (
                mongo_meta.get("thumbnail_url") or
                mongo_meta.get("drive_url") or
                payload.get("drive_url") or
                payload.get("file_path") or
                payload.get("face_thumbnail") or
                ""
            )
            resolved_thumb = resolve_image_thumbnail(raw_thumb)

            match_entry = {
                "image_id": image_id,
                "person_id": person_id,
                "similarity_score": round(raw_sim, 4),
                "re_ranked_confidence": round(weighted_conf, 4),
                "person_name": mongo_meta.get("person_name", person_id.replace("_", " ").title()),
                "role": mongo_meta.get("role", "Registered Subject"),
                "department": mongo_meta.get("department", "Organization"),
                "thumbnail_url": resolved_thumb,
                "face_crop": payload.get("face_thumbnail", ""),
                "enrollment_quality": mongo_meta.get("quality_score", 0.85)
            }

            re_ranked_matches.append(match_entry)

            if weighted_conf > highest_confidence:
                highest_confidence = weighted_conf
                best_match = match_entry

        # STRICT REQUIREMENT: Completely omit any vector match below threshold (0.45)
        valid_matches = [
            m for m in re_ranked_matches
            if m["similarity_score"] >= settings.RECOGNITION_SIMILARITY_THRESHOLD
        ]
        valid_matches.sort(key=lambda m: m["similarity_score"], reverse=True)

        match_found = bool(
            valid_matches and
            valid_matches[0]["similarity_score"] >= settings.RECOGNITION_SIMILARITY_THRESHOLD
        )

        best_match = valid_matches[0] if match_found else None

        return {
            "match_found": match_found,
            "person_id": str(best_match["person_id"]) if match_found else None,
            "person_metadata": best_match if match_found else None,
            "similarity_score": float(best_match["similarity_score"]) if match_found else 0.0,
            "overall_confidence": round(float(best_match["re_ranked_confidence"]) * 100.0, 2) if match_found else 0.0,
            "top_matches": valid_matches[:settings.MAX_TOP_MATCHES],
            "recognition_status": "MATCH_FOUND" if match_found else "NO_MATCH"
        }


    async def _fetch_person_metadata(self, image_id: str, person_id: str) -> Dict[str, Any]:
        """Queries MongoDB for person profile and enrollment metadata."""
        if mongo_db.db is None:
            return {}

        try:
            doc = await mongo_db.db.image_metadata.find_one(
                {"$or": [{"image_id": image_id}, {"person_id": person_id}]}
            )
            if doc:
                raw_path = doc.get("file_path") or doc.get("relative_folder") or ""
                return {
                    "person_name": doc.get("person_name", doc.get("original_filename", person_id)),
                    "role": doc.get("role", "Verified User"),
                    "department": doc.get("department", "Security Division"),
                    "thumbnail_url": raw_path,
                    "quality_score": doc.get("quality_score", 0.90)
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metadata from MongoDB for image {image_id}: {e}")

        return {}



confidence_service = ConfidenceService()
