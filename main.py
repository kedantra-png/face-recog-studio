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
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Ensure repository root is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.anti_spoof_predict import AntiSpoofPredict
from src.generate_patches import CropImage
from src.utility import parse_model_name
from test_model import pad_to_aspect_ratio_3_4

# Load environment configuration variables
REAL_THRESHOLD = float(os.getenv("REAL_THRESHOLD", "0.35"))
MODEL_DIR = os.getenv("MODEL_DIR", os.path.join(os.path.dirname(__file__), "resources", "anti_spoof_models"))
SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "images", "sample")
DEVICE_ID = int(os.getenv("DEVICE_ID", "0"))
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


app = FastAPI(
    title="Silent-Face Anti-Spoofing API",
    description="FastAPI Backend for Live & Image Face Anti-Spoofing Detection",
    version="2.0.0",
)

# Configure robust CORS middleware allowing all local frontend origins & WebSockets
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal Server Error"},
        headers={
            "Access-Control-Allow-Origin": "*",
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
from src.pipeline.services.embedding_service import embedding_service
from src.pipeline.websocket.manager import ws_manager
from fastapi import WebSocket, WebSocketDisconnect

# Include Pipeline API v2 Routers
app.include_router(pipeline_router)
app.include_router(recognition_router)


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




@app.on_event("startup")
async def startup_event():
    """Startup handler connecting databases, launching worker pool, warming up AI models, and recovering stuck tasks."""
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

    # Warm up InsightFace embedding engine and MiniFASNet anti-spoof model in RAM
    try:
        embedding_service.warmup()
    except Exception as e:
        logger.warning(f"Embedding warmup warning: {e}")


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



@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown handler closing worker tasks and DB connections."""
    await worker_pool.stop()
    await mongo_db.close()


# Global lazy loaded predictor and cropper
predictor = None
cropper = CropImage()


def get_predictor():
    global predictor
    if predictor is None:
        predictor = AntiSpoofPredict(DEVICE_ID)
    return predictor


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
    if image is None or image.size == 0:
        return {"success": False, "error": "Invalid image payload or corrupted image format"}

    padded_img, (pad_x, pad_y) = pad_to_aspect_ratio_3_4(image)
    model_pred_instance = get_predictor()
    bbox = model_pred_instance.get_bbox(padded_img)

    if bbox == [0, 0, 1, 1] or bbox[2] <= 0 or bbox[3] <= 0:
        return {
            "success": False,
            "error": "No face detected in the frame. Please position face clearly within view.",
            "image_name": img_name
        }

    model_files = [f for f in os.listdir(MODEL_DIR) if f.endswith('.pth')]
    if not model_files:
        return {"success": False, "error": f"No model weights found in directory: {MODEL_DIR}"}

    prediction = np.zeros((1, 3))
    per_model_scores = {}
    cropped_patches = {}
    total_time = 0

    for model_name in model_files:
        h_input, w_input, model_type, scale = parse_model_name(model_name)
        param = {
            "org_img": padded_img,
            "bbox": bbox,
            "scale": scale,
            "out_w": w_input,
            "out_h": h_input,
            "crop": True,
        }
        if scale is None:
            param["crop"] = False

        cropped_img = cropper.crop(**param)
        patch_key = f"scale_{scale if scale is not None else 'full'}"
        cropped_patches[patch_key] = cv2_to_base64(cropped_img)

        start = time.time()
        model_path = os.path.join(MODEL_DIR, model_name)
        model_pred = model_pred_instance.predict(cropped_img, model_path)
        cost = time.time() - start
        total_time += cost

        prediction += model_pred
        real_score = float(model_pred[0][1])
        per_model_scores[model_name] = {
            "model_type": model_type,
            "scale": scale,
            "real_score": round(real_score * 100, 2),
            "fake_score": round((1.0 - real_score) * 100, 2),
            "latency_ms": round(cost * 1000, 1)
        }

    num_models = len(model_files)
    final_probs = prediction[0] / num_models
    real_prob = float(final_probs[1])
    fake_prob = float(final_probs[0] + final_probs[2])

    # Direct Comparison Rule: Calculate both real and spoof scores across models.
    # If spoof_prob >= real_prob, or if any scale model fake_score > real_score, verdict is SPOOF.
    any_model_spoof_dominant = any(m_data["fake_score"] > m_data["real_score"] for m_data in per_model_scores.values())
    is_real = (real_prob > fake_prob) and (real_prob >= REAL_THRESHOLD) and (not any_model_spoof_dominant)
    label = 1 if is_real else 0
    score = real_prob if is_real else fake_prob

    result_label = "REAL FACE" if is_real else "FAKE / SPOOF ATTACK"
    color = (0, 215, 0) if is_real else (0, 0, 235)  # BGR

    annotated = padded_img.copy()
    x, y, w, h = bbox
    cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 3)

    label_text = f"{result_label}: {real_prob * 100:.1f}%"
    font_scale = max(0.5, min(1.0, annotated.shape[0] / 800.0))
    cv2.putText(annotated, label_text, (x, max(25, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 2)

    return {
        "success": True,
        "is_real": is_real,
        "label": label,
        "label_str": result_label,
        "score": round(score * 100, 2),
        "real_probability": round(real_prob * 100, 2),
        "fake_probability": round(fake_prob * 100, 2),
        "threshold_used": REAL_THRESHOLD,
        "bbox": {"x": bbox[0], "y": bbox[1], "width": bbox[2], "height": bbox[3]},
        "per_model_scores": per_model_scores,
        "total_latency_ms": round(total_time * 1000, 1),
        "annotated_image_b64": cv2_to_base64(annotated),
        "cropped_patches": cropped_patches,
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
    model_files = [f for f in os.listdir(MODEL_DIR) if f.endswith('.pth')] if os.path.exists(MODEL_DIR) else []
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
