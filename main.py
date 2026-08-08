# -*- coding: utf-8 -*-
"""
Silent-Face-Anti-Spoofing FastAPI Backend API Service
------------------------------------------------------
Pure REST API service providing Real-Time Anti-Spoofing Detection,
Image Upload Analysis, Sample Image Evaluation, and Threshold Configuration.
No UI is served from this backend. All frontend interactions are managed
via API calls from the Next.js application.
"""

import os
import sys
import time
import base64
import logging
import numpy as np
import cv2
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

logger = logging.getLogger("main")


# Load environment configuration from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, Request, File, UploadFile, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, RedirectResponse
from pydantic import BaseModel

# Ensure repository root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.pipeline.config import settings
from src.pipeline.storage.drive_service import drive_service

# Load environment configuration variables
REAL_THRESHOLD = float(os.getenv("REAL_THRESHOLD", "0.35"))
MODEL_DIR = os.path.join(os.path.dirname(__file__), "resources", "anti_spoof_models")
DEVICE_ID = 0
SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "images", "sample")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

ALLOWED_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]
CORS_ORIGINS = ALLOWED_CORS_ORIGINS


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler connecting databases, warming up AI models, recovering stuck tasks, and performing graceful shutdown."""
    try:
        await mongo_db.connect()
    except Exception as e:
        logger.warning(f"MongoDB connection warning on startup: {e}")

    try:
        await qdrant_service.connect()
    except Exception as e:
        logger.warning(f"Qdrant connection warning on startup: {e}")

    try:
        await worker_pool.start()
    except Exception as e:
        logger.warning(f"Worker pool startup warning: {e}")

    # Pre-load AI models into RAM and launch dynamic idle watchdog
    try:
        from src.pipeline.services.model_lifecycle_manager import model_lifecycle_manager
        model_lifecycle_manager.load_all_models()
        model_lifecycle_manager.start_idle_watchdog()
    except Exception as e:
        logger.warning(f"Model Lifecycle Manager startup warning: {e}")

    # Auto-create MongoDB indexes for studios and events collections
    if mongo_db.db is not None:
        try:
            await mongo_db.db.studios.create_index("studio_id", unique=True)
            await mongo_db.db.events.create_index("event_id", unique=True)
            await mongo_db.db.events.create_index("studio_id")
        except Exception as idx_err:
            logger.warning(f"Studio/Events index creation warning: {idx_err}")

    # Auto-recover any images stuck in 'queued' state from earlier worker restarts
    if mongo_db.db is not None:
        try:
            queued_docs = await mongo_db.db.image_metadata.find({"embedding_status": "queued"}).to_list(1000)
            if queued_docs:
                from src.pipeline.queue.background_queue import background_queue
                logger.info(f"Auto-recovering {len(queued_docs)} queued images for InsightFace embedding generation...")
                for doc in queued_docs:
                    fpath = doc.get("file_path", "")
                    if fpath and os.path.exists(fpath):
                        await background_queue.enqueue(
                            task_type="generate_embedding",
                            payload={
                                "image_id": doc["image_id"],
                                "file_path": fpath,
                                "relative_path": doc.get("relative_folder", "")
                            },
                            job_id=doc.get("job_id", "recovered_job"),
                            priority=2
                        )
        except Exception as e:
            logger.warning(f"Task recovery warning: {e}")

    yield

    # Graceful shutdown handler
    await worker_pool.stop()
    await mongo_db.close()


app = FastAPI(
    title="Silent-Face Anti-Spoofing API",
    description="FastAPI Backend for Live & Image Face Anti-Spoofing Detection",
    version="2.0.0",
    lifespan=lifespan,
)

# Configure robust CORS middleware allowing all local network frontend origins & WebSockets with credentials support
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def normalize_double_slashes(request: Request, call_next):
    """Normalizes any double slashes in incoming request paths from DevTunnels or proxies."""
    if "//" in request.scope.get("path", ""):
        request.scope["path"] = request.scope["path"].replace("//", "/")
    response = await call_next(request)
    return response


from fastapi import Request

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global uncaught exception on {request.url}: {exc}", exc_info=True)
    origin = request.headers.get("origin") or "http://localhost:3000"
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal Server Error"},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )



# Pipeline Services & Router Imports
from src.pipeline.db.mongo import mongo_db
from src.pipeline.db.qdrant_service import qdrant_service
from src.pipeline.workers.manager import worker_pool
from src.pipeline.api.routes import router as pipeline_router
from src.pipeline.api.recognition_routes import router as recognition_router
from src.pipeline.api.master_routes import router as master_router
from src.pipeline.services.embedding_service import embedding_service
from src.pipeline.services.anti_spoof_service import anti_spoof_service
from src.pipeline.websocket.manager import ws_manager
from fastapi import WebSocket, WebSocketDisconnect

# Include Pipeline API v2 Routers
app.include_router(pipeline_router)
app.include_router(recognition_router)
app.include_router(master_router)


@app.websocket("/ws/upload/{client_id}")
@app.websocket("/api/v2/ws/upload/{client_id}")
async def root_websocket_endpoint(websocket: WebSocket, client_id: str):
    """Root & API v2 WebSocket endpoint broadcasting real-time queue & telemetry updates."""
    await ws_manager.connect(client_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)


@app.websocket("/api/v2/ws/recognition/{session_id}")
@app.websocket("/ws/recognition/{session_id}")
async def recognition_websocket_root(websocket: WebSocket, session_id: str):
    """Recognition WebSocket endpoint broadcasting live recognition stage updates."""
    await ws_manager.connect(session_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)







def cv2_to_base64(img, format=".jpg"):
    _, buffer = cv2.imencode(format, img)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"


def decode_base64_image(b64_str: str):
    if "," in b64_str:
        b64_str = b64_str.split(",")[1]
    img_bytes = base64.b64decode(b64_str)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img


def process_image(image: np.ndarray, img_name: str = "uploaded_image") -> Dict[str, Any]:
    from src.pipeline.services.model_lifecycle_manager import model_lifecycle_manager
    from src.pipeline.services.face_processor import face_processor
    from src.pipeline.services.anti_spoof_service import anti_spoof_service
    from src.pipeline.services.liveness_motion_service import liveness_motion_service

    model_lifecycle_manager.touch_activity()

    if image is None or image.size == 0:
        return {"success": False, "error": "Invalid image payload or corrupted image format"}

    start_time = time.time()
    faces = face_processor.process_image(image)

    if not faces:
        return {
            "success": False,
            "error": "No face detected in the frame. Please position face clearly within view.",
            "image_name": img_name
        }

    best_face = max(faces, key=lambda f: f.get("confidence", 0.0))
    bbox = best_face.get("bbox", [0, 0, 1, 1])
    landmarks = best_face.get("landmarks")

    motion_res = liveness_motion_service.analyze_landmark_motion([landmarks])
    liveness_res = anti_spoof_service.predict_multi_frame([image], face_bboxes=[bbox], motion_analysis=motion_res)

    is_real = liveness_res.get("is_real", False)
    real_prob = float(liveness_res.get("real_confidence", 0.95))
    fake_prob = float(liveness_res.get("spoof_confidence", 0.05))
    total_time = round((time.time() - start_time) * 1000, 1)

    result_label = "REAL FACE" if is_real else "FAKE / SPOOF ATTACK"
    color = (0, 215, 0) if is_real else (0, 0, 235)  # BGR

    annotated = image.copy()
    x, y, w, h = bbox
    cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 3)

    label_text = f"{result_label}: {real_prob * 100:.1f}%"
    font_scale = max(0.5, min(1.0, annotated.shape[0] / 800.0))
    cv2.putText(annotated, label_text, (x, max(25, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 2)

    return {
        "success": True,
        "is_real": is_real,
        "label": 1 if is_real else 0,
        "label_str": result_label,
        "score": round(real_prob * 100, 2),
        "real_probability": round(real_prob * 100, 2),
        "fake_probability": round(fake_prob * 100, 2),
        "threshold_used": REAL_THRESHOLD,
        "bbox": {"x": bbox[0], "y": bbox[1], "width": bbox[2], "height": bbox[3]},
        "per_model_scores": {
            "Landmark_Deformability_Engine": {
                "model_type": "Landmark_Deformability",
                "scale": 1.0,
                "real_score": round(real_prob * 100, 2),
                "fake_score": round(fake_prob * 100, 2),
                "latency_ms": total_time
            }
        },
        "total_latency_ms": total_time,
        "annotated_image_b64": cv2_to_base64(annotated),
        "cropped_patches": {},
        "image_name": img_name
    }


class ImagePayload(BaseModel):
    image_b64: str


@app.get("/")
@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "Silent-Face Anti-Spoofing FastAPI Backend",
        "real_threshold": REAL_THRESHOLD,
        "device_id": DEVICE_ID,
        "model_dir": MODEL_DIR,
        "allowed_origins": CORS_ORIGINS
    }


@app.get("/api/config")
def get_config():
    model_files = [f for f in os.listdir(MODEL_DIR) if f.endswith('.pth') and ('MiniFASNet' in f or 'org' in f or 'x' in f)] if os.path.exists(MODEL_DIR) else []
    return {
        "real_threshold": REAL_THRESHOLD,
        "device_id": DEVICE_ID,
        "model_dir": MODEL_DIR,
        "available_models": model_files,
        "num_models": len(model_files),
        "cors_origins": CORS_ORIGINS
    }


@app.get("/api/samples")
def get_samples():
    samples = []
    if os.path.exists(SAMPLE_DIR):
        for f in sorted(os.listdir(SAMPLE_DIR)):
            if f.lower().endswith(('.jpg', '.png', '.jpeg', '.webp')) and not f.endswith('_result.jpg'):
                is_real_hint = "Real" if "T" in f else "Spoof/Fake" if "F" in f else "Sample"
                samples.append({
                    "filename": f,
                    "url": f"/api/sample_image/{f}",
                    "hint": is_real_hint
                })
    return {"success": True, "samples": samples}


@app.get("/api/sample_image/{filename}")
def serve_sample_image(filename: str):
    file_path = os.path.join(SAMPLE_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Sample image not found")
    return FileResponse(file_path)


@app.get("/api/v2/images/{image_id:path}/stream")
async def stream_binary_image_by_id(image_id: str):
    """
    High-performance Binary Blob Streaming Endpoint.
    Serves full-resolution binary image files directly from local disk or Google Drive API,
    with HTTP 304 Caching and Cache-Control headers for zero-CPU instant browser rendering.
    """
    cleaned_id = image_id.replace("file://", "").replace("\\", "/").strip()
    target_name = os.path.basename(cleaned_id)

    # 1. Direct disk path resolution
    if os.path.exists(cleaned_id) and os.path.isfile(cleaned_id):
        return FileResponse(cleaned_id, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    alt_disk_path = os.path.join(os.getcwd(), cleaned_id)
    if os.path.exists(alt_disk_path) and os.path.isfile(alt_disk_path):
        return FileResponse(alt_disk_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    temp_dir = getattr(settings, "TEMP_UPLOAD_DIR", getattr(settings, "TEMP_DIR", "temp_uploads"))
    temp_path = os.path.join(temp_dir, target_name)
    if os.path.exists(temp_path) and os.path.isfile(temp_path):
        return FileResponse(temp_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    # 2. Recursive local disk search in temp_uploads
    if target_name and os.path.exists(temp_dir):
        for root, _, files in os.walk(temp_dir):
            if target_name in files:
                full_match = os.path.join(root, target_name)
                return FileResponse(full_match, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    # 3. Query MongoDB & Stream Binary Blob from Google Drive API
    if mongo_db.db is not None:
        try:
            doc = await mongo_db.db.image_metadata.find_one({
                "$or": [
                    {"image_id": image_id},
                    {"_id": image_id},
                    {"person_id": image_id},
                    {"filename": image_id},
                    {"internal_filename": {"$regex": str(target_name)}}
                ]
            })
            if doc:
                file_path = doc.get("file_path", "")
                clean_path = file_path.replace("file://", "").replace("\\", "/").strip()
                if os.path.exists(clean_path) and os.path.isfile(clean_path):
                    return FileResponse(clean_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

                # Fetch Google Drive binary blob via drive_service
                drive_file_id = doc.get("drive_file_id")
                if drive_file_id and drive_service.service:
                    content_bytes = await drive_service.download_file_bytes(drive_file_id)
                    if content_bytes:
                        return Response(content=content_bytes, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

                drive_url = doc.get("drive_url")
                if drive_url and ("drive.google.com" in drive_url or "googleusercontent.com" in drive_url):
                    if "/file/d/" in drive_url:
                        d_id = drive_url.split("/file/d/")[1].split("/")[0]
                        return RedirectResponse(url=f"https://lh3.googleusercontent.com/d/{d_id}=s0")
                    elif "id=" in drive_url:
                        d_id = drive_url.split("id=")[1].split("&")[0]
                        return RedirectResponse(url=f"https://lh3.googleusercontent.com/d/{d_id}=s0")
        except Exception as e:
            logger.warning(f"Error querying image metadata for {image_id}: {e}")

    raise HTTPException(status_code=404, detail="Binary image file not found")


@app.get("/api/v2/images/{image_id:path}/download")
async def download_binary_image_by_id(image_id: str):
    """
    Dedicated 1-Click Original Image Download Endpoint.
    Serves full-resolution original binary image files with Content-Disposition: attachment header.
    """
    cleaned_id = image_id.replace("file://", "").replace("\\", "/").strip()
    target_name = os.path.basename(cleaned_id)

    # 1. Direct local disk search
    if os.path.exists(cleaned_id) and os.path.isfile(cleaned_id):
        return FileResponse(cleaned_id, media_type="image/jpeg", filename=target_name)

    alt_disk_path = os.path.join(os.getcwd(), cleaned_id)
    if os.path.exists(alt_disk_path) and os.path.isfile(alt_disk_path):
        return FileResponse(alt_disk_path, media_type="image/jpeg", filename=target_name)

    temp_dir = getattr(settings, "TEMP_UPLOAD_DIR", getattr(settings, "TEMP_DIR", "temp_uploads"))
    temp_path = os.path.join(temp_dir, target_name)
    if os.path.exists(temp_path) and os.path.isfile(temp_path):
        return FileResponse(temp_path, media_type="image/jpeg", filename=target_name)

    # 2. Recursive search in temp_uploads
    if target_name and os.path.exists(temp_dir):
        for root, _, files in os.walk(temp_dir):
            if target_name in files:
                full_match = os.path.join(root, target_name)
                return FileResponse(full_match, media_type="image/jpeg", filename=target_name)

    # 3. Query MongoDB & Stream Binary Blob from Google Drive API
    if mongo_db.db is not None:
        try:
            doc = await mongo_db.db.image_metadata.find_one({
                "$or": [
                    {"image_id": image_id},
                    {"_id": image_id},
                    {"person_id": image_id},
                    {"filename": image_id},
                    {"internal_filename": {"$regex": str(target_name)}}
                ]
            })
            if doc:
                file_path = doc.get("file_path", "")
                clean_path = file_path.replace("file://", "").replace("\\", "/").strip()
                if os.path.exists(clean_path) and os.path.isfile(clean_path):
                    return FileResponse(clean_path, media_type="image/jpeg", filename=doc.get("original_filename", target_name))

                drive_file_id = doc.get("drive_file_id")
                if drive_file_id and drive_service.service:
                    content_bytes = await drive_service.download_file_bytes(drive_file_id)
                    if content_bytes:
                        headers = {"Content-Disposition": f'attachment; filename="{doc.get("original_filename", target_name)}"'}
                        return Response(content=content_bytes, media_type="image/jpeg", headers=headers)
        except Exception as e:
            logger.warning(f"Error serving download for {image_id}: {e}")

    raise HTTPException(status_code=404, detail="Binary image file not found for download")


@app.get("/temp_uploads/{path:path}")
async def serve_or_fetch_temp_upload(path: str):
    """
    Serves uploaded images from local disk if present.
    If local file is missing, queries MongoDB / Google Drive API to download and serve the file seamlessly.
    """
    clean_relative = path.replace("\\", "/").strip("/")
    local_path = os.path.join("temp_uploads", clean_relative)

    # 1. Local disk hit
    if os.path.exists(local_path) and os.path.isfile(local_path):
        return FileResponse(local_path)

    alt_local_path = os.path.join(os.getcwd(), "temp_uploads", clean_relative)
    if os.path.exists(alt_local_path) and os.path.isfile(alt_local_path):
        return FileResponse(alt_local_path)

    filename = os.path.basename(clean_relative)
    temp_dir = getattr(settings, "TEMP_UPLOAD_DIR", getattr(settings, "TEMP_DIR", "temp_uploads"))
    if filename and os.path.exists(temp_dir):
        for root, _, files in os.walk(temp_dir):
            if filename in files:
                full_match = os.path.join(root, filename)
                return FileResponse(full_match, headers={"Cache-Control": "public, max-age=86400"})

    drive_file_id = None
    drive_url = None

    # 2. Query MongoDB for file metadata & drive_file_id
    if mongo_db.db is not None:
        try:
            doc = await mongo_db.db.image_metadata.find_one({
                "$or": [
                    {"internal_filename": filename},
                    {"original_filename": filename},
                    {"file_path": {"$regex": filename}}
                ]
            })
            if doc:
                drive_file_id = doc.get("drive_file_id")
                drive_url = doc.get("drive_url")
        except Exception as err:
            logger.warning(f"Error searching MongoDB for file {filename}: {err}")

    # 3. Fallback: Search Google Drive by filename directly if not found in MongoDB
    if not drive_file_id and drive_service.service:
        drive_res = await drive_service.search_file_by_name(filename)
        if drive_res:
            drive_file_id = drive_res.get("drive_file_id")
            drive_url = drive_res.get("drive_url")

    # 4. Download file from Google Drive if drive_file_id is available
    if drive_file_id and drive_service.service:
        content_bytes = await drive_service.download_file_bytes(drive_file_id)
        if content_bytes:
            try:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                with open(local_path, "wb") as f:
                    f.write(content_bytes)
            except Exception as cache_err:
                logger.warning(f"Failed to cache downloaded file to local disk: {cache_err}")

            mime_type = "image/jpeg"
            if filename.lower().endswith(".png"):
                mime_type = "image/png"
            elif filename.lower().endswith(".webp"):
                mime_type = "image/webp"

            return Response(content=content_bytes, media_type=mime_type)

    # 5. If drive_url is a direct view link, redirect
    if drive_url and ("drive.google.com" in drive_url or "googleusercontent.com" in drive_url):
        if "/file/d/" in drive_url:
            d_id = drive_url.split("/file/d/")[1].split("/")[0]
            cdn_url = f"https://lh3.googleusercontent.com/d/{d_id}=s0"
            return RedirectResponse(url=cdn_url)

    logger.warning(f"File not found on local disk or Google Drive: {path}")
    raise HTTPException(status_code=404, detail="Image file not found on local storage or Google Drive")



from fastapi import FastAPI, HTTPException, Request

@app.post("/api/predict")
async def predict(request: Request):
    try:
        content_type = request.headers.get("content-type", "")

        if "multipart/form-data" in content_type:
            form = await request.form()
            file_obj = form.get("file")
            if file_obj and hasattr(file_obj, "read"):
                file_bytes = await file_obj.read()
                nparr = np.frombuffer(file_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                filename = getattr(file_obj, "filename", "uploaded_file")
                return process_image(img, img_name=filename)

        elif "application/json" in content_type:
            data = await request.json()
            if isinstance(data, dict) and "image_b64" in data:
                img = decode_base64_image(data["image_b64"])
                return process_image(img, img_name="webcam_frame")

        raise HTTPException(status_code=400, detail="Missing valid file or image_b64 payload")

    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "error": str(e)}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
