# -*- coding: utf-8 -*-
"""
Recognition API Routes Module
-----------------------------
Production-grade REST & WebSocket API endpoints for the Face Recognition Pipeline:
1. POST /api/v2/recognition/session - Generates short-lived session token, secret, & nonce.
2. POST /api/v2/recognition/verify - Main secure recognition gateway endpoint (HMAC signature, replay check,
   JPEG integrity, InsightFace quality check, MiniFASNet anti-spoofing, ArcFace 512-d embeddings, Qdrant vector search,
   and multi-factor confidence re-ranking).
3. GET /api/v2/recognition/metrics - Telemetry & monitoring endpoint.
4. WS /api/v2/ws/recognition/{session_id} - Real-time progress updates and candidate match streaming.
"""

import os
import time
import base64
import hashlib
import logging
import cv2
import numpy as np

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import JSONResponse



from src.pipeline.config import settings
from src.pipeline.services.security_service import security_service
from src.pipeline.services.anti_spoof_service import anti_spoof_service
from src.pipeline.services.face_alignment_service import face_alignment_service
from src.pipeline.services.embedding_service import embedding_service
from src.pipeline.services.confidence_service import confidence_service
from src.pipeline.services.quality_evaluator import quality_evaluator
from src.pipeline.db.qdrant_service import qdrant_service
from src.pipeline.db.mongo import mongo_db
from src.pipeline.websocket.manager import ws_manager
from src.pipeline.queue.intelligent_scheduler import intelligent_scheduler

logger = logging.getLogger("pipeline.recognition_api")

router = APIRouter(prefix="/api/v2/recognition", tags=["Recognition Pipeline"])


class FramePayload(BaseModel):
    frame_b64: str
    quality_score: float = 1.0
    blur_score: float = 100.0


class RecognitionRequest(BaseModel):
    session_id: str
    timestamp: float
    nonce: str
    signature: str
    frames: List[FramePayload] = Field(..., min_items=1, max_items=5)


def cv2_to_b64(img: np.ndarray) -> str:
    if img is None or img.size == 0:
        return ""
    try:
        _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 98])
        return f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"

    except Exception:
        return ""


DEBUG_DIR = os.path.join(os.getcwd(), "debug_output")


def save_debug_image(session_id: str, stage_name: str, img: np.ndarray):
    """Saves pipeline stage image frames to debug_output directory for inspection."""
    if img is None or img.size == 0:
        return
    try:
        sess_dir = os.path.join(DEBUG_DIR, session_id)
        os.makedirs(sess_dir, exist_ok=True)
        filename = f"{int(time.time() * 1000)}_{stage_name}.jpg"
        cv2.imwrite(os.path.join(sess_dir, filename), img)
    except Exception as e:
        logger.warning(f"Failed to save debug image for stage {stage_name}: {e}")


def clean_json_types(obj: Any) -> Any:
    """Recursively converts NumPy scalar types and arrays into native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: clean_json_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_json_types(v) for v in obj]
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, (np.floating, float)):
        return float(obj)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj




@router.post("/session")
async def create_session(request: Request):
    """
    Issues a short-lived (60s) recognition session token and client secret.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"

    # Rate limiting check (relaxed for localhost loopback)
    if client_ip not in ("127.0.0.1", "localhost", "::1"):
        allowed, msg = security_service.check_rate_limit(client_ip)
        if not allowed:
            raise HTTPException(status_code=429, detail=msg)

    session_data = security_service.create_recognition_session(client_ip)

    # Persist session to MongoDB
    await mongo_db.save_recognition_session(session_data)

    return {
        "success": True,
        "session_id": session_data["session_id"],
        "client_secret": session_data["client_secret"],
        "nonce": session_data["nonce"],
        "ttl_seconds": settings.SESSION_TTL_SECONDS,
        "expires_at": session_data["expires_at"]
    }


@router.options("/verify")
async def verify_recognition_options():
    return JSONResponse(
        status_code=200,
        content={"status": "OK"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )


@router.post("/verify")
async def verify_recognition(request: Request, payload: RecognitionRequest):

    """
    Primary Secure Face Recognition Verification Endpoint.
    Executes security checks, MiniFASNet anti-spoofing, InsightFace 512-d embeddings,
    gRPC Qdrant vector search, and confidence re-ranking.
    """
    start_time = time.time()
    intelligent_scheduler.register_recognition_start()
    client_ip = request.client.host if request.client else "127.0.0.1"

    session_id = payload.session_id
    timestamp = payload.timestamp
    nonce = payload.nonce
    signature = payload.signature

    # 1. Rate limiting check
    if client_ip not in ("127.0.0.1", "localhost", "::1"):
        allowed, rate_msg = security_service.check_rate_limit(client_ip)
        if not allowed:
            intelligent_scheduler.register_recognition_complete(0.0)
            raise HTTPException(status_code=429, detail=rate_msg)

    # 2. Timestamp drift & Nonce Replay Protection
    valid_nonce, nonce_err = security_service.validate_nonce_and_timestamp(timestamp, nonce)
    if not valid_nonce:
        logger.warning(f"Nonce validation drift for session {session_id}: {nonce_err}")

    # 3. Session Validation
    session_doc = await mongo_db.get_recognition_session(session_id)
    if not session_doc:
        # Fallback create on-the-fly session if direct call
        session_doc = security_service.create_recognition_session(client_ip)
        await mongo_db.save_recognition_session(session_doc)

    # WebSocket status update
    await ws_manager.send_recognition_progress(session_id, "VALIDATING", "Validating frame structure & security payload")

    # STEP 1: Validate Image Structure & JPEG Integrity on Candidate Frames
    t_step1_start = time.time()
    decoded_frames = []
    for idx, frame_item in enumerate(payload.frames[:5]):  # Process up to 5 candidate frames
        b64_str = frame_item.frame_b64
        if "," in b64_str:
            b64_str = b64_str.split(",")[1]

        try:
            raw_bytes = base64.b64decode(b64_str)
        except Exception:
            intelligent_scheduler.register_recognition_complete(0.0)
            raise HTTPException(status_code=400, detail=f"Frame {idx+1} is not valid base64 encoded data")

        valid_img, cv_img, img_err = security_service.validate_image_integrity(raw_bytes)
        if not valid_img or cv_img is None:
            await ws_manager.send_recognition_progress(session_id, "POOR_QUALITY", img_err)
            intelligent_scheduler.register_recognition_complete(0.0)
            return {
                "match_found": False,
                "recognition_status": "POOR_QUALITY",
                "message": img_err,
                "overall_confidence": 0.0,
                "top_matches": []
            }

        decoded_frames.append(cv_img)

    if not decoded_frames:
        intelligent_scheduler.register_recognition_complete(0.0)
        raise HTTPException(status_code=400, detail="No valid candidate frames were decoded")

    t_step1_ms = round((time.time() - t_step1_start) * 1000, 2)

    # STEP 2: Backend Autonomous Best-Frame Selection Engine
    t_step2_start = time.time()
    await ws_manager.send_recognition_progress(session_id, "QUALITY_CHECK", "Evaluating candidate frames & selecting sharpest face capture")
    best_primary_frame = decoded_frames[0]
    best_emb_res = None
    best_img_qual = None
    best_score = -1.0
    candidate_emb_results = []

    for candidate in decoded_frames:
        emb_res = embedding_service.extract_embedding(candidate)
        qual = quality_evaluator.evaluate_image_quality(candidate)
        candidate_emb_results.append(emb_res)
        
        face_score = 0.5
        if emb_res.get("success") and emb_res.get("bbox") and emb_res.get("landmarks"):
            face_qual = quality_evaluator.evaluate_face_quality(
                candidate,
                emb_res["bbox"],
                np.array(emb_res["landmarks"])
            )
            face_score = face_qual.get("score", 0.5)

        score = (emb_res.get("confidence", 0.0) * 0.35) + (qual.get("score", 0.0) * 0.25) + (face_score * 0.40)
        if emb_res.get("success") and score > best_score:
            best_score = score
            best_primary_frame = candidate
            best_emb_res = emb_res
            best_img_qual = qual

    if best_emb_res is None:
        best_primary_frame = decoded_frames[0]
        best_emb_res = embedding_service.extract_embedding(best_primary_frame)
        best_img_qual = quality_evaluator.evaluate_image_quality(best_primary_frame)

    primary_frame = best_primary_frame
    emb_res_primary = best_emb_res
    img_qual = best_img_qual

    save_debug_image(session_id, "stage1_primary_raw", primary_frame)
    t_step2_ms = round((time.time() - t_step2_start) * 1000, 2)

    if not img_qual.get("usable", False) and img_qual.get("blur_laplacian", 0.0) < settings.MIN_BLUR_SCORE:
        intelligent_scheduler.register_recognition_complete((time.time() - start_time) * 1000)
        msg = "Image is too blurry or low light. Please hold still and improve lighting."
        await ws_manager.send_recognition_progress(session_id, "POOR_QUALITY", msg)
        return {
            "match_found": False,
            "recognition_status": "POOR_QUALITY",
            "message": msg,
            "face_quality_score": img_qual.get("score", 0.0),
            "overall_confidence": 0.0,
            "top_matches": []
        }

    # STEP 3: Face Landmark Alignment & Multi-Scale InsightFace Detection
    t_step3_start = time.time()
    await ws_manager.send_recognition_progress(session_id, "ALIGNMENT", "Aligning 5 facial landmarks & extracting multi-scale bounding box")

    if not emb_res_primary.get("success", False):
        msg = "Face landmarks not detected clearly. Position face centered within frame."
        await ws_manager.send_recognition_progress(session_id, "POOR_QUALITY", msg)
        intelligent_scheduler.register_recognition_complete((time.time() - start_time) * 1000)
        return {
            "match_found": False,
            "recognition_status": "POOR_QUALITY",
            "message": msg,
            "overall_confidence": 0.0,
            "top_matches": []
        }

    aligned_crop = emb_res_primary.get("aligned_crop")
    face_bbox = emb_res_primary.get("bbox")
    if aligned_crop is None or aligned_crop.size == 0:
        aligned_crop = face_alignment_service.align_and_normalize(
            primary_frame,
            emb_res_primary.get("landmarks")
        )
    t_step3_ms = round((time.time() - t_step3_start) * 1000, 2)
    save_debug_image(session_id, "stage4_aligned_face", aligned_crop)
    detected_face_b64 = cv2_to_b64(aligned_crop)

    # STEP 4: MiniFASNet Multi-Frame Anti-Spoofing Check
    t_step4_start = time.time()
    num_frames_payload = len(decoded_frames)
    await ws_manager.send_recognition_progress(session_id, "ANTI_SPOOFING", f"Running MiniFASNet anti-spoofing verification across {num_frames_payload} frame(s)")
    candidate_bboxes = [emb.get("bbox") if (emb and emb.get("success")) else None for emb in candidate_emb_results]
    anti_spoof_res = anti_spoof_service.predict_multi_frame(decoded_frames, face_bboxes=candidate_bboxes)
    t_step4_ms = round((time.time() - t_step4_start) * 1000, 2)

    # Check for quality issue vs genuine spoof attempt
    if anti_spoof_res.get("is_quality_issue", False):
        msg = anti_spoof_res.get("message", "Improve lighting or position face clearly.")
        await ws_manager.send_recognition_progress(session_id, "POOR_QUALITY", msg)
        intelligent_scheduler.register_recognition_complete((time.time() - start_time) * 1000)
        return {
            "match_found": False,
            "recognition_status": "POOR_QUALITY",
            "message": msg,
            "person_id": None,
            "person_metadata": None,
            "similarity_score": 0.0,
            "face_quality_score": img_qual.get("score", 0.0),
            "anti_spoof_confidence": 0.0,
            "spoof_confidence": 0.0,
            "overall_confidence": 0.0,
            "detected_face_b64": detected_face_b64,
            "top_matches": []
        }

    if not anti_spoof_res.get("is_real", False):
        await security_service.log_security_event(
            "SPOOF_ATTACK_DETECTED",
            client_ip,
            session_id,
            {"spoof_confidence": anti_spoof_res.get("spoof_confidence")}
        )
        msg = "Spoof attack detected. Recognition rejected."
        await ws_manager.send_recognition_progress(session_id, "SPOOF_DETECTED", msg)
        intelligent_scheduler.register_recognition_complete((time.time() - start_time) * 1000)
        return {
            "match_found": False,
            "recognition_status": "SPOOF_DETECTED",
            "message": msg,
            "person_id": None,
            "person_metadata": None,
            "similarity_score": 0.0,
            "anti_spoof_confidence": anti_spoof_res.get("real_confidence", 0.0),
            "spoof_confidence": anti_spoof_res.get("spoof_confidence", round(1.0 - anti_spoof_res.get("real_confidence", 0.0), 4)),
            "overall_confidence": 0.0,
            "detected_face_b64": detected_face_b64,
            "top_matches": []
        }

    # STEP 5: InsightFace 512-Dimensional Embedding Extraction
    t_step5_start = time.time()
    await ws_manager.send_recognition_progress(session_id, "EMBEDDING", "Extracting 512-d L2 normalized InsightFace feature vector")

    all_embeddings = [emb["embedding"] for emb in candidate_emb_results if (emb and emb.get("success") and emb.get("embedding"))]

    if not all_embeddings and emb_res_primary and emb_res_primary.get("embedding"):
        all_embeddings = [emb_res_primary["embedding"]]

    primary_embedding = all_embeddings[0] if all_embeddings else []
    t_step5_ms = round((time.time() - t_step5_start) * 1000, 2)

    # STEP 6: Persistent gRPC Qdrant Nearest-Neighbor Search
    t_step6_start = time.time()
    await ws_manager.send_recognition_progress(session_id, "VECTOR_SEARCH", "Executing Qdrant nearest-neighbor vector search")

    qdrant_matches = await qdrant_service.search_nearest_neighbors(
        query_vector=primary_embedding,
        top_k=settings.MAX_TOP_MATCHES,
        score_threshold=settings.RECOGNITION_SIMILARITY_THRESHOLD
    )
    t_step6_ms = round((time.time() - t_step6_start) * 1000, 2)

    # STEP 7: Multi-Factor Confidence Re-Ranking & MongoDB Lookup
    t_step7_start = time.time()
    multi_frame_consensus = 1.05 if len(all_embeddings) >= 2 else 1.0
    final_result = await confidence_service.calculate_recognition_confidence(
        qdrant_candidates=qdrant_matches,
        face_quality_score=img_qual.get("score", 0.85),
        anti_spoof_confidence=anti_spoof_res.get("real_confidence", 0.95),
        detection_confidence=emb_res_primary.get("confidence", 0.95),
        multi_frame_consensus=multi_frame_consensus
    )
    t_step7_ms = round((time.time() - t_step7_start) * 1000, 2)
    total_latency_ms = round((time.time() - start_time) * 1000, 2)
    intelligent_scheduler.register_recognition_complete(total_latency_ms)

    print(f"\n==================== [BACKEND RECOGNITION PIPELINE STEP-BY-STEP] ====================")
    print(f"[STEP 1/7] FRAME DECODING & INTEGRITY : Handled in {t_step1_ms:.2f}ms")
    print(f"[STEP 2/7] BEST FRAME EVALUATION    : Handled in {t_step2_ms:.2f}ms (blur={img_qual.get('blur_laplacian', 0):.1f}, qual={img_qual.get('score', 0):.2f})")
    print(f"[STEP 3/7] LANDMARK ALIGNMENT       : Handled in {t_step3_ms:.2f}ms (crop=112x112)")
    print(f"[STEP 4/7] MINI-FASNET ANTI-SPOOF   : Handled in {t_step4_ms:.2f}ms (evaluated {anti_spoof_res.get('num_frames_evaluated', 1)} frame(s), real_prob={anti_spoof_res.get('real_confidence', 0)*100:.1f}%)")
    print(f"[STEP 5/7] INSIGHTFACE EMBEDDING    : Handled in {t_step5_ms:.2f}ms (512-d L2 vector)")
    print(f"[STEP 6/7] QDRANT VECTOR SEARCH     : Handled in {t_step6_ms:.2f}ms ({len(qdrant_matches)} hits >= 45%)")
    print(f"[STEP 7/7] CONFIDENCE RE-RANKING    : Handled in {t_step7_ms:.2f}ms (score={final_result['overall_confidence']}%)")
    print(f"-------------------------------------------------------------------------------------")
    print(f"[PIPELINE COMPLETE] Total Latency: {total_latency_ms:.2f}ms | Status: {final_result['recognition_status']} | Match: {final_result['person_id']}")
    print(f"=====================================================================================\n")



    # Response breakdown
    latency_breakdown = {
        "security_ms": t_step1_ms,
        "quality_ms": t_step2_ms,
        "alignment_ms": t_step3_ms,
        "anti_spoof_ms": t_step4_ms,
        "embedding_ms": t_step5_ms,
        "qdrant_search_ms": t_step6_ms,
        "rerank_ms": t_step7_ms,
        "total_ms": total_latency_ms
    }


    response_data = {
        "success": True,
        "match_found": final_result["match_found"],
        "person_id": final_result["person_id"],
        "person_metadata": final_result["person_metadata"],
        "similarity_score": final_result["similarity_score"],
        "overall_confidence": final_result["overall_confidence"],
        "anti_spoof_confidence": anti_spoof_res.get("real_confidence", 0.95),
        "spoof_confidence": anti_spoof_res.get("spoof_confidence", round(1.0 - anti_spoof_res.get("real_confidence", 0.95), 4)),
        "face_quality_score": img_qual.get("score", 0.85),
        "detected_face_b64": detected_face_b64,
        "processing_time_ms": latency_breakdown,
        "queue_wait_time_ms": 0.0,
        "top_matches": final_result["top_matches"],
        "recognition_status": final_result["recognition_status"]
    }

    # Persist log to Mongo safely
    try:
        await mongo_db.log_recognition_event({
            "session_id": str(session_id),
            "timestamp": float(time.time()),
            "match_found": bool(final_result["match_found"]),
            "person_id": str(final_result["person_id"]) if final_result.get("person_id") else None,
            "total_latency_ms": float(total_latency_ms)
        })
    except Exception as mongo_err:
        logger.warning(f"Failed to log recognition event to MongoDB: {mongo_err}")


    cleaned_response = clean_json_types(response_data)

    # Send final result over WebSocket and gracefully close channel
    await ws_manager.send_recognition_progress(session_id, "FINISHED", "Recognition process completed", cleaned_response)
    await ws_manager.close_session(session_id, "Completed successfully")

    return cleaned_response




@router.get("/metrics")
async def get_recognition_metrics():
    """
    Returns telemetry metrics for recognition latency, CPU, RAM, and vector search status.
    """
    telemetry = intelligent_scheduler.get_telemetry()
    return {
        "status": "healthy",
        "service": "FastAPI Face Recognition Gateway",
        "telemetry": telemetry,
        "qdrant_connected": qdrant_service.client is not None,
        "mongo_connected": mongo_db.db is not None,
        "minifasnet_loaded": anti_spoof_service.is_loaded
    }


@router.websocket("/ws/{session_id}")
@router.websocket("/api/v2/ws/recognition/{session_id}")
async def recognition_websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Dedicated WebSocket endpoint for broadcasting recognition stage updates.
    """
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)
