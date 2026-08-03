# Face Recognition & Anti-Spoofing Studio — Architecture & API Documentation

This document provides complete technical documentation for the two main application sections: **`/` (Live Camera Search & Recognition)** and **`/upload` (Bulk Dataset Upload & Vector Embedding Indexing)**. It details all associated REST APIs, WebSocket channels, data transfer protocols, security handshakes, and code implementations.

---

## 1. Executive System Overview

```
+-----------------------------------------------------------------------------------+
|                                  NEXT.JS FRONTEND                                  |
|   +---------------------------------------+   +-------------------------------+   |
|   |   Route: / (Live Search & Recognition) |   |   Route: /upload (Bulk Upload)|   |
|   +---------------------------------------+   +-------------------------------+   |
+-----------------------------------||----------------------------------------------+
                                    || HTTP REST & WebSockets (FastAPI / Uvicorn)
+-----------------------------------\/----------------------------------------------+
|                               FASTAPI BACKEND API                                 |
|                                                                                   |
|  +---------------------------+  +---------------------------+  +----------------+ |
|  | Anti-Spoofing Engine      |  | Embedding Engine          |  | Resumable      | |
|  | MiniFASNet (Multi-scale)  |  | InsightFace (512-d ArcFace)|  | Chunk Storage  | |
|  +---------------------------+  +---------------------------+  +----------------+ |
+-----------------------------------||----------------------------------------------+
                                    || Storage & Vector Databases
+-----------------------------------\/----------------------------------------------+
|  +--------------------------------+       +------------------------------------+  |
|  | Qdrant Vector Database          |       | MongoDB Metadata Database          |  |
|  | Collection: `faces_embed_v2`   |       | DB: `face_recog_db_v2`             |  |
|  +--------------------------------+       +------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 2. Section 1: `/` (User Live Camera Search & Recognition)

### 2.1 Section Purpose & Workflow
The `/` route is the primary real-time verification gateway. Users interact with their local webcam via WebRTC. Frames are extracted, scored for image quality (sharpness, lighting, pose), and sent to the backend alongside a cryptographic session signature (HMAC-SHA256). The backend verifies anti-spoofing (MiniFASNet), computes 512-d face embeddings (InsightFace ArcFace), searches vector embeddings in Qdrant, and returns matching identity profiles with confidence scores.

---

### 2.2 APIs Included in `/` (User Search Section)

#### 1. Runtime System Configuration
* **Endpoint**: `GET /api/config`
* **Description**: Returns live system parameters, model weights directory, device ID (GPU/CPU), anti-spoof decision threshold (`REAL_THRESHOLD`), and CORS policies.
* **Response**:
```json
{
  "real_threshold": 0.35,
  "device_id": 0,
  "model_dir": "resources/anti_spoof_models",
  "available_models": ["2.7_80x80_MiniFASNetV2.pth", "1.0_80x80_MiniFASNetV1SE.pth"],
  "num_models": 2,
  "cors_origins": ["http://localhost:3000", "http://127.0.0.1:3000"]
}
```

---

#### 2. Create Recognition Cryptographic Session
* **Endpoint**: `POST /api/v2/recognition/session`
* **Description**: Generates a short-lived (60s TTL) session token, `client_secret`, and cryptographic `nonce` to prevent replay attacks.
* **Response**:
```json
{
  "success": true,
  "session_id": "sec_sess_8f9a2b1c4e",
  "client_secret": "c9e782f0a1...",
  "nonce": "n_4a82b9e1",
  "ttl_seconds": 60,
  "expires_at": 1722706000.0
}
```

---

#### 3. Live Face Verification & Recognition
* **Endpoint**: `POST /api/v2/recognition/verify`
* **Description**: Primary security and recognition endpoint. Accepts high-performance zero-overhead binary JPEG Blobs via `multipart/form-data` (or legacy Base64 JSON strings via `application/json`). Verifies anti-spoofing, extracts 512-d ArcFace embeddings, performs Qdrant vector search, and calculates multi-factor confidence.
* **Headers**: `Content-Type: multipart/form-data` (Recommended) or `application/json` (Fallback)
* **Payload Structure (Binary Blob / Multipart FormData)**:
  * `session_id` (Text Form Field): Cryptographic session token
  * `timestamp` (Text Form Field): Client Unix epoch timestamp
  * `nonce` (Text Form Field): Single-use security nonce
  * `signature` (Text Form Field): HMAC-SHA256 signature
  * `files` (Binary File Stream): Raw JPEG Blob images (`canvas.toBlob()`)
* **Payload Structure (Base64 JSON Fallback)**:
```json
{
  "session_id": "sec_sess_8f9a2b1c4e",
  "timestamp": 1722705945.12,
  "nonce": "n_4a82b9e1",
  "signature": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "frames": [
    {
      "frame_b64": "data:image/jpeg;base64,/9j/4AAQSkZJRg...",
      "quality_score": 0.94,
      "blur_score": 142.5
    }
  ]
}
```
* **Response**:
```json
{
  "success": true,
  "is_real": true,
  "anti_spoof_score": 98.4,
  "match_found": true,
  "person_id": "EMP_1042",
  "person_metadata": {
    "name": "Jane Doe",
    "department": "Engineering"
  },
  "similarity_score": 0.895,
  "overall_confidence": 0.942,
  "latency_ms": {
    "anti_spoof_ms": 18.4,
    "embedding_ms": 22.1,
    "qdrant_ms": 6.8,
    "total_ms": 47.3
  }
}
```

---

#### 4. Real-Time Recognition WebSocket
* **Endpoint**: `WS /api/v2/ws/recognition/{session_id}`
* **Description**: Broadcasts real-time pipeline status updates (`VALIDATING`, `ANTI_SPOOFING`, `EMBEDDING_EXTRACTION`, `QDRANT_SEARCH`, `COMPLETED`) to the browser while processing a verification request.

---

#### 5. Basic Prediction / Legacy Single Image Test
* **Endpoint**: `POST /api/predict`
* **Description**: Direct single-frame Anti-Spoofing classification via `multipart/form-data` or JSON payload containing `image_b64`.

---

#### 6. Preset Sample Images Retrieval
* **Endpoints**: `GET /api/samples`, `GET /api/sample_image/{filename}`
* **Description**: Returns sample test images for evaluation and manual demo testing.

---

## 3. Section 2: `/upload` (Bulk Dataset Upload & Vector Embedding Indexing)

### 3.1 Section Purpose & Workflow
The `/upload` page provides administrative dataset management, bulk folder/ZIP uploads, resumable chunked streaming, worker queue visualization, background InsightFace 512-d vector indexing into Qdrant & MongoDB, direct search debugging, and paginated upload logs.

---

### 3.2 APIs Included in `/upload` (Upload Section)

#### 1. Resumable Chunked Upload Endpoint
* **Endpoint**: `POST /api/v2/upload/chunk`
* **Description**: Streams 5MB file chunks directly to disk. Once all chunks land, it automatically triggers an asynchronous background worker task (`upload_process`).
* **Payload**: `multipart/form-data`
  * `job_id` (str): Unique bulk upload job identifier.
  * `file_id` (str): Unique file hash / ID.
  * `chunk_index` (int): Current 0-based chunk index.
  * `total_chunks` (int): Total chunks for the file.
  * `relative_path` (str): Relative folder path.
  * `chunk` (file): Binary 5MB slice.
* **Response**:
```json
{
  "success": true,
  "job_id": "job_9x2k71a",
  "file_id": "file_a8d910",
  "chunk_index": 0,
  "total_chunks": 3,
  "saved_chunks": 1,
  "is_assembled": false
}
```

---

#### 2. Direct ZIP Archive Upload
* **Endpoint**: `POST /api/v2/upload/zip`
* **Description**: Accepts `.zip` archives, extracts image directories safely on the server, and enqueues images into the worker pipeline.

---

#### 3. Upload Job Telemetry & Status
* **Endpoint**: `GET /api/v2/upload/job/{job_id}`
* **Description**: Returns progress status, completed image count, detected face count, and database indexing progress for a given `job_id`.

---

#### 4. Paginated Upload History & Metadata Search
* **Endpoint**: `GET /api/v2/uploads`
* **Description**: Fetches paginated image records stored in MongoDB with filters for filename search and embedding status (`queued`, `embedding_processing`, `completed`, `failed`).
* **Query Parameters**: `page=1`, `limit=20`, `query=john`, `status=completed`

---

#### 5. Direct Image Search Debugger
* **Endpoint**: `POST /api/v2/upload/search-debug`
* **Description**: Accepts a single uploaded test image, extracts the 512-d ArcFace vector using InsightFace, queries Qdrant directly, and returns nearest neighbor matches and step-by-step latency breakdowns.

---

#### 6. Database Reset & Maintenance Admin Utility
* **Endpoints**: `GET /admin/clean-databases`, `POST /admin/clean-databases`
* **Description**: Clears MongoDB metadata collections and drops Qdrant vector collections for clean database re-initialization.

---

#### 7. Real-Time Telemetry & Upload Queue WebSocket
* **Endpoint**: `WS /api/v2/ws/upload/{client_id}`
* **Description**: Pushes real-time system metrics (CPU/RAM usage, active queue count, worker status) and live task state changes (`embedding_processing`, `embedding_completed`).

---

## 4. Camera Video Capture & Data Transfer Mechanism

### 4.1 Step-by-Step Data Flow

```
[Webcam Hardware] 
       │ (WebRTC MediaStream: 1280x720 @ 30FPS)
       ▼
[<video> HTML5 Element] ── (Offscreen Canvas 2D) ──► [Frame Selection & Blur Check]
                                                            │
                                    ┌───────────────────────┘ (Pick Best 3 Candidate Frames)
                                    ▼
                         [Base64 JPEG Encoding]
                                    │ (toDataURL('image/jpeg', 0.95))
                                    ▼
                         [SHA256 / HMAC Security Sign]
                                    │ (HMAC-SHA256 using client_secret)
                                    ▼
                         [POST /api/v2/recognition/verify]
                                    │
    ┌───────────────────────────────┴───────────────────────────────┐
    ▼                                                               ▼
[MiniFASNet Anti-Spoofing]                             [InsightFace 512-d ArcFace]
(Cropped Multi-Scale Patches)                          (5-Landmark Alignment + Vector Extraction)
    │                                                               │
    └───────────────────────────────┬───────────────────────────────┘
                                    ▼
                         [Qdrant Cosine Similarity]
                         (Collection: faces_embed_v2)
                                    │
                                    ▼
                         [JSON Verification Result]
```

### 4.2 How the Transfer Works
1. **WebRTC Stream Setup**: The browser calls `navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 } })` to obtain the video feed.
2. **Canvas Frame Capture**: An animation loop draws frames onto an offscreen `<canvas>`.
3. **Quality & Blur Evaluation**: The frontend computes image brightness, contrast, and Laplacian variance (sharpness score) on the pixel buffer to drop blurry frames.
4. **Encoding to Base64 Data URL**: The canvas converts selected candidate frames to JPEG strings (`data:image/jpeg;base64,...`).
5. **Cryptographic Session Handshake**:
   - Client calls `POST /api/v2/recognition/session` to obtain `session_id`, `client_secret`, and `nonce`.
   - Client computes HMAC-SHA256: `HMAC(client_secret, timestamp + ":" + nonce + ":" + session_id)`.
6. **API Transmission & Decoding**:
   - JSON payload is POSTed to `/api/v2/recognition/verify`.
   - Backend strips `data:image/jpeg;base64,`, decodes raw bytes using `base64.b64decode()`, and converts bytes into OpenCV BGR arrays via `cv2.imdecode(nparr, cv2.IMREAD_COLOR)`.

---

## 5. Code Examples

### 5.1 Frontend Camera Frame Extraction & Selection (TypeScript / React)

```typescript
// frontend/src/components/SecureWebcamScanner.tsx
import React, { useRef, useEffect } from 'react';

export function captureCandidateFrames(
  videoEl: HTMLVideoElement,
  canvasEl: HTMLCanvasElement,
  count: number = 3
): Array<{ frame_b64: string; quality_score: number; blur_score: number }> {
  const ctx = canvasEl.getContext('2d');
  if (!ctx || !videoEl.videoWidth) return [];

  canvasEl.width = videoEl.videoWidth;
  canvasEl.height = videoEl.videoHeight;

  const candidateFrames = [];
  
  for (let i = 0; i < count; i++) {
    ctx.drawImage(videoEl, 0, 0, canvasEl.width, canvasEl.height);
    const dataUrl = canvasEl.toDataURL('image/jpeg', 0.95);
    
    // Simple blur heuristic (variance calculation placeholder)
    const blurScore = 120.0 + Math.random() * 30.0;
    
    candidateFrames.push({
      frame_b64: dataUrl,
      quality_score: 0.95,
      blur_score: blurScore
    });
  }

  return candidateFrames;
}
```

---

### 5.2 Frontend Session Handshake & HMAC Signing (TypeScript)

```typescript
// frontend/src/hooks/useRecognitionSession.ts
async function hmacSha256Hex(keyStr: string, messageStr: string): Promise<string> {
  const encoder = new TextEncoder();
  const keyData = encoder.encode(keyStr);
  const msgData = encoder.encode(messageStr);
  
  const key = await crypto.subtle.importKey(
    'raw', 
    keyData, 
    { name: 'HMAC', hash: 'SHA-256' }, 
    false, 
    ['sign']
  );
  
  const signature = await crypto.subtle.sign('HMAC', key, msgData);
  const hashArray = Array.from(new Uint8Array(signature));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function submitVerification(session: any, frames: any[]) {
  const timestamp = Date.now() / 1000;
  const message = `${timestamp}:${session.nonce}:${session.session_id}`;
  const signature = await hmacSha256Hex(session.client_secret, message);

  const response = await fetch('http://127.0.0.1:8000/api/v2/recognition/verify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: session.session_id,
      timestamp,
      nonce: session.nonce,
      signature,
      frames
    })
  });

  return await response.json();
}
```

---

### 5.3 Frontend Resumable 5MB Chunked Uploader (TypeScript)

```typescript
// frontend/src/components/upload/ResumableUploader.ts
const CHUNK_SIZE = 5 * 1024 * 1024; // 5 MB

export async function uploadFileInChunks(file: File, jobId: string, fileId: string) {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

  for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
    const start = chunkIndex * CHUNK_SIZE;
    const end = Math.min(file.size, start + CHUNK_SIZE);
    const chunkBlob = file.slice(start, end);

    const formData = new FormData();
    formData.append('job_id', jobId);
    formData.append('file_id', fileId);
    formData.append('chunk_index', chunkIndex.toString());
    formData.append('total_chunks', totalChunks.toString());
    formData.append('relative_path', file.name);
    formData.append('chunk', chunkBlob, file.name);

    const res = await fetch('http://127.0.0.1:8000/api/v2/upload/chunk', {
      method: 'POST',
      body: formData,
    });
    
    const result = await res.json();
    console.log(`Chunk ${chunkIndex + 1}/${totalChunks} uploaded:`, result);
  }
}
```

---

### 5.4 Backend Base64 Decoding & Processing Pipeline (FastAPI / Python)

```python
# main.py & src/pipeline/api/recognition_routes.py
import base64
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException

app = FastAPI()

def decode_base64_frame(b64_str: str) -> np.ndarray:
    """Strips data URL header and decodes base64 string into OpenCV BGR image matrix."""
    if "," in b64_str:
        b64_str = b64_str.split(",")[1]
    
    img_bytes = base64.b64decode(b64_str)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise ValueError("Failed to decode image from base64 buffer")
    return img

@app.post("/api/predict")
async def predict_single_frame(payload: dict):
    b64_img = payload.get("image_b64")
    if not b64_img:
        raise HTTPException(status_code=400, detail="Missing image_b64")
    
    cv_img = decode_base64_frame(b64_img)
    
    # Process image matrix: MiniFASNet anti-spoof prediction
    # ...
    return {
        "success": True,
        "image_shape": cv_img.shape,
        "is_real": True,
        "real_score": 98.5
    }
```

---

## 6. API Summary Reference Matrix

| Endpoint | Method | Section | Primary Purpose | Security / Protocols |
| :--- | :--- | :--- | :--- | :--- |
| `/api/config` | `GET` | `/` & `/upload` | Configuration & status | Public REST |
| `/api/v2/recognition/session` | `POST` | `/` | Issue recognition session token | Rate Limited |
| `/api/v2/recognition/verify` | `POST` | `/` | Anti-spoof + 512-d Embedding Search | HMAC-SHA256, Nonce, Base64 |
| `/api/v2/ws/recognition/{id}` | `WS` | `/` | Real-time verification progress | WebSocket |
| `/api/predict` | `POST` | `/` | Basic Anti-Spoof single-frame test | Base64 / Multipart |
| `/api/samples` | `GET` | `/` | Fetch test image filenames | Public REST |
| `/api/sample_image/{name}` | `GET` | `/` | Serve test sample JPEG | Public REST |
| `/api/v2/upload/chunk` | `POST` | `/upload` | 5MB resumable chunked file stream | Multipart, SHA256 deduplication |
| `/api/v2/upload/zip` | `POST` | `/upload` | Bulk ZIP archive upload | Multipart stream |
| `/api/v2/upload/job/{id}` | `GET` | `/upload` | Check job progress status | Public REST |
| `/api/v2/uploads` | `GET` | `/upload` | Paginated MongoDB metadata search | Query Params |
| `/api/v2/upload/search-debug` | `POST` | `/upload` | Direct Qdrant search debugger | Multipart |
| `/admin/clean-databases` | `GET`/`POST` | `/upload` | Clear MongoDB & reset Qdrant | Admin REST |
| `/api/v2/ws/upload/{client_id}` | `WS` | `/upload` | System metrics & worker updates | WebSocket |

---
*Documentation compiled for Silent-Face Anti-Spoofing & InsightFace Recognition Gateway.*
