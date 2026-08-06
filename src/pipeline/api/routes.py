# -*- coding: utf-8 -*-
"""
Pipeline REST & WebSocket Router
--------------------------------
Provides production API endpoints for resumable chunk uploads, ZIP archives,
job control, paginated upload history, telemetry metrics, and real-time WebSockets.
"""

import os
import time
import uuid
import shutil
import logging
import cv2
import numpy as np
import base64
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, WebSocket, WebSocketDisconnect, Query
from src.pipeline.config import settings
from src.pipeline.db.mongo import mongo_db
from src.pipeline.storage.disk_storage import disk_storage
from src.pipeline.queue.background_queue import background_queue
from src.pipeline.websocket.manager import ws_manager
from src.pipeline.services.embedding_service import embedding_service
from src.pipeline.services.confidence_service import confidence_service
from src.pipeline.db.qdrant_service import qdrant_service

logger = logging.getLogger("pipeline.api")

router = APIRouter(prefix="/api/v2", tags=["Pipeline API"])



@router.post("/upload/chunk")
async def upload_chunk(
    job_id: str = Form(...),
    file_id: str = Form(...),
    chunk_index: int = Form(...),
    total_chunks: int = Form(...),
    relative_path: str = Form(...),
    is_zip: bool = Form(False),
    chunk: UploadFile = File(...)
):
    """
    Resumable chunked upload endpoint.
    Streams 5MB chunks directly to disk and triggers background processing upon last chunk.
    """
    try:
        chunk_bytes = await chunk.read()
        if not chunk_bytes:
            raise HTTPException(status_code=400, detail="Empty chunk payload received")

        # Save chunk to disk
        await disk_storage.save_chunk(job_id, file_id, chunk_index, chunk_bytes)

        # Check if last chunk received
        job_dir = disk_storage.get_job_dir(job_id)
        chunk_dir = os.path.join(job_dir, "chunks", file_id)
        saved_chunks = len(os.listdir(chunk_dir)) if os.path.exists(chunk_dir) else 0

        is_assembled = False
        if saved_chunks >= total_chunks:
            # Enqueue upload worker task
            await background_queue.enqueue(
                task_type="upload_process",
                payload={
                    "file_id": file_id,
                    "total_chunks": total_chunks,
                    "relative_path": relative_path,
                    "is_zip": is_zip
                },
                job_id=job_id,
                priority=1
            )
            is_assembled = True

        return {
            "success": True,
            "job_id": job_id,
            "file_id": file_id,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "saved_chunks": saved_chunks,
            "is_assembled": is_assembled
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chunk {chunk_index} for file {file_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload/zip")
async def upload_zip_archive(
    job_id: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    """Direct ZIP archive upload endpoint."""
    try:
        if not job_id:
            job_id = f"job_{uuid.uuid4().hex[:12]}"

        job_dir = disk_storage.get_job_dir(job_id)
        zip_path = os.path.join(job_dir, "original", file.filename or "archive.zip")

        # Stream ZIP to disk
        with open(zip_path, "wb") as f:
            while chunk := await file.read(65536):
                f.write(chunk)

        # Security validation
        is_valid, mime = disk_storage.validate_security(zip_path)
        if not is_valid:
            os.remove(zip_path)
            raise HTTPException(status_code=400, detail=f"ZIP security validation failed: {mime}")

        # Enqueue ZIP extraction task
        await background_queue.enqueue(
            task_type="upload_process",
            payload={"file_path": zip_path, "is_zip": True},
            job_id=job_id,
            priority=1
        )

        return {"success": True, "job_id": job_id, "filename": file.filename}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upload/job/{job_id}")
async def get_job_status(job_id: str):
    """Retrieves processing status and stats for a given upload job."""
    if mongo_db.db is None:
        return {"success": True, "job_id": job_id, "status": "processing"}

    job = await mongo_db.get_job(job_id)
    images = await mongo_db.db.image_metadata.find({"job_id": job_id}).to_list(1000)

    total_images = len(images)
    completed = len([i for i in images if i.get("embedding_status") == "completed"])
    detected_faces = sum([i.get("detected_faces", 0) for i in images])

    return {
        "success": True,
        "job_id": job_id,
        "status": job.get("status", "processing") if job else "processing",
        "total_images": total_images,
        "completed_images": completed,
        "total_detected_faces": detected_faces,
        "images": images
    }


@router.get("/uploads")
async def get_upload_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: Optional[str] = None,
    status: Optional[str] = None
):
    """Paginated search & filter endpoint for processed images and quality scores."""
    if mongo_db.db is None:
        return {"success": True, "page": page, "total": 0, "images": []}

    filter_query: Dict[str, Any] = {}
    if query:
        filter_query["original_filename"] = {"$regex": query, "$options": "i"}
    if status:
        filter_query["embedding_status"] = status

    skip = (page - 1) * limit
    total = await mongo_db.db.image_metadata.count_documents(filter_query)
    cursor = mongo_db.db.image_metadata.find(filter_query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit)
    images = await cursor.to_list(limit)

    return {
        "success": True,
        "page": page,
        "limit": limit,
        "total": total,
        "images": images
    }


@router.post("/upload/search-debug")
async def debug_direct_image_search(file: UploadFile = File(...)):
    """
    Direct Image Embedding & Vector Search Debugging Endpoint.
    Directly converts uploaded image to 512-d ArcFace embedding and searches Qdrant (faces_embed_v2).
    """
    start_time = time.time()
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty image payload")

    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Could not decode image format")

    t_emb_start = time.time()
    emb_res = embedding_service.extract_embedding(img)
    t_emb_ms = round((time.time() - t_emb_start) * 1000, 2)

    if not emb_res.get("success") or not emb_res.get("embedding"):
        return {
            "success": False,
            "error": "No face detected in uploaded image for embedding generation",
            "extracted_ms": t_emb_ms,
            "qdrant_ms": 0.0,
            "total_ms": round((time.time() - start_time) * 1000, 2),
            "top_matches": []
        }

    query_vec = emb_res["embedding"]
    aligned_crop = emb_res.get("aligned_crop")
    detected_face_b64 = ""
    if aligned_crop is not None and aligned_crop.size > 0:
        _, buf = cv2.imencode(".jpg", aligned_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 98])
        detected_face_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"


    t_qdrant_start = time.time()
    qdrant_hits = await qdrant_service.search_nearest_neighbors(
        query_vector=query_vec,
        top_k=settings.MAX_TOP_MATCHES,
        score_threshold=settings.RECOGNITION_SIMILARITY_THRESHOLD
    )

    t_qdrant_ms = round((time.time() - t_qdrant_start) * 1000, 2)

    t_conf_start = time.time()
    conf_res = await confidence_service.calculate_recognition_confidence(
        qdrant_candidates=qdrant_hits,
        face_quality_score=0.90,
        anti_spoof_confidence=0.98,
        detection_confidence=emb_res.get("confidence", 0.95)
    )
    t_conf_ms = round((time.time() - t_conf_start) * 1000, 2)
    total_ms = round((time.time() - start_time) * 1000, 2)

    print(f"\n==================== [DIRECT SEARCH DEBUGGER PIPELINE] ====================")
    print(f"[STEP 1/3] INSIGHTFACE 512-D EMBEDDING: Extracted vector in {t_emb_ms}ms")
    print(f"[STEP 2/3] QDRANT VECTOR SEARCH     : Searched '{settings.QDRANT_COLLECTION}' in {t_qdrant_ms}ms ({len(qdrant_hits)} hits >= 45%)")
    print(f"[STEP 3/3] CONFIDENCE RE-RANKING    : Ranked candidates in {t_conf_ms}ms (match={conf_res['match_found']})")
    print(f"---------------------------------------------------------------------------")
    print(f"[SEARCH COMPLETE] Total Latency: {total_ms}ms | Person: {conf_res['person_id']}")
    print(f"===========================================================================\n")

    return {
        "success": True,
        "match_found": conf_res["match_found"],
        "person_id": conf_res["person_id"],
        "person_metadata": conf_res["person_metadata"],
        "similarity_score": conf_res["similarity_score"],
        "overall_confidence": conf_res["overall_confidence"],
        "detected_face_b64": detected_face_b64,
        "top_matches": conf_res["top_matches"],
        "latency_ms": {
            "extract_ms": t_emb_ms,
            "qdrant_ms": t_qdrant_ms,
            "total_ms": total_ms
        }
    }



@router.get("/admin/clean-databases")
@router.post("/admin/clean-databases")
async def clean_databases_endpoint():

    """
    Admin Endpoint: Completely wipes all MongoDB face databases and resets Qdrant vector collections.
    """
    dropped_mongo = []
    dropped_qdrant = []

    # 1. Clean MongoDB
    if mongo_db.client is not None:
        dbs = ["face_recog_db_v2", "face_recog_db_final", "face_recognition_db", "auraface_db"]
        existing = await mongo_db.client.list_database_names()
        for db_name in dbs:
            if db_name in existing:
                await mongo_db.client.drop_database(db_name)
                dropped_mongo.append(db_name)

        # Re-initialize fresh indexes
        db_v2 = mongo_db.client["face_recog_db_v2"]
        await db_v2.image_metadata.create_index("image_id", unique=True)
        await db_v2.image_metadata.create_index("created_at")

    # 2. Clean Qdrant Vector DB
    if qdrant_service.client is not None:
        try:
            cols_res = await qdrant_service.client.get_collections()
            col_names = [c.name for c in cols_res.collections]
            for col in ["faces_embed_v2", "faces_embed"]:
                if col in col_names:
                    await qdrant_service.client.delete_collection(col)
                    dropped_qdrant.append(col)

            # Re-create fresh faces_embed_v2
            from qdrant_client.http import models as rest_models
            await qdrant_service.client.create_collection(
                collection_name="faces_embed_v2",
                vectors_config=rest_models.VectorParams(
                    size=512,
                    distance=rest_models.Distance.COSINE
                )
            )
        except Exception as e:
            logger.warning(f"Error resetting Qdrant collections: {e}")

    # 3. Clean Temp Uploads & Debug Disk Storage
    cleaned_disk = []
    for disk_dir in ["temp_uploads", "debug_output"]:
        if os.path.exists(disk_dir):
            try:
                shutil.rmtree(disk_dir, ignore_errors=True)
                os.makedirs(disk_dir, exist_ok=True)
                cleaned_disk.append(disk_dir)
            except Exception as e:
                logger.warning(f"Error purging disk directory {disk_dir}: {e}")

    # 4. Clean Google Drive Files
    cleaned_drive_files = 0
    try:
        from src.pipeline.storage.drive_service import drive_service
        if drive_service and drive_service.service and drive_service.parent_folder_id:
            import asyncio
            loop = asyncio.get_event_loop()
            query = f"'{drive_service.parent_folder_id}' in parents and trashed = false"
            res = await loop.run_in_executor(
                None,
                lambda: drive_service.service.files().list(q=query, fields="files(id, name)", pageSize=1000).execute()
            )
            files = res.get("files", [])
            for f in files:
                fid = f.get("id")
                try:
                    await loop.run_in_executor(
                        None,
                        lambda file_id=fid: drive_service.service.files().delete(fileId=file_id).execute()
                    )
                    cleaned_drive_files += 1
                except Exception as del_err:
                    logger.warning(f"Error deleting drive file {fid}: {del_err}")
    except Exception as drive_err:
        logger.warning(f"Error cleaning Google Drive storage: {drive_err}")

    return {
        "success": True,
        "message": "MongoDB databases, Qdrant vector collections, disk storage, and Google Drive files successfully reset to clean state.",
        "dropped_mongo_dbs": dropped_mongo,
        "dropped_qdrant_collections": dropped_qdrant,
        "cleaned_disk_directories": cleaned_disk,
        "cleaned_google_drive_files": cleaned_drive_files
    }



@router.get("/admin/drive-email")
async def get_drive_email_info():
    """Returns the authenticated Google Drive user account email and display name."""
    from src.pipeline.storage.drive_service import drive_service
    if not drive_service or not drive_service.service:
        return {"configured": False, "email": None, "message": "Google Drive service not initialized"}
    try:
        about = drive_service.service.about().get(fields="user").execute()
        user_info = about.get("user", {})
        return {
            "configured": True,
            "email": user_info.get("emailAddress"),
            "display_name": user_info.get("displayName")
        }
    except Exception as e:
        return {"configured": False, "error": str(e)}


@router.get("/health")



@router.get("/metrics")
async def get_system_health():
    """System health telemetry endpoint."""
    import psutil
    queue_metrics = await background_queue.get_queue_metrics()
    return {
        "status": "healthy",
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_free_gb": round(psutil.disk_usage("/").free / (1024 ** 3), 2),
        "queue": queue_metrics,
        "mongo_connected": mongo_db.db is not None
    }


@router.websocket("/ws/upload/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """Real-time WebSocket endpoint broadcasting queue & worker updates."""
    await ws_manager.connect(client_id, websocket)
    try:
        while True:
            # Keep-alive receive loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)
