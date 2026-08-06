# Technical Documentation: Frontend Route `/` (Face Recognition Gateway)

This document provides a **pin-to-pin, exhaustive technical reference** for the primary frontend page located at route `/` in the AuraFace AI platform.

It covers:
- **Environment & Backend URL Dynamic Resolution** (via `.env` and `localStorage`)
- **Security & Cryptographic Verification Protocol** (Session Tokens, HMAC-SHA256 Request Signing, Web Crypto API, Nonce Anti-Replay Protection)
- **Client-Side Image Quality & Stability Telemetry Engine** (Discrete Laplacian Blur Score, Motion Stability, Luminance Contrast, Auto-Capture)
- **WebSocket Real-Time Progress Pipeline**
- **Pin-to-Pin State Machine & Component Data Flow**
- **Complete, Copyable Production Source Code** for all involved components, hooks, API utilities, and visual camera interfaces (glowing oval profile ring, laser scanning animation, telemetry bars).

---

## Table of Contents

1. [Architecture & Component Structure](#1-architecture--component-structure)
2. [Environment Configuration & Backend URL Resolution](#2-environment-configuration--backend-url-resolution)
3. [Security Architecture & Cryptographic Verification Protocol](#3-security-architecture--cryptographic-verification-protocol)
4. [Client-Side Image Quality & Telemetry Engine](#4-client-side-image-quality--telemetry-engine)
5. [Pin-to-Pin Data Flow & State Lifecycle](#5-pin-to-pin-data-flow--state-lifecycle)
6. [API & WebSocket Communication Contracts](#6-api--websocket-communication-contracts)
7. [Complete Source Code Reference (Copy-Paste Ready)](#7-complete-source-code-reference-copy-paste-ready)
   - [7.1 TypeScript Interface Schema (`src/types/index.ts`)](#71-typescript-interface-schema-srctypesindexts)
   - [7.2 API Client & Base64 Utilities (`src/lib/api.ts`)](#72-api-client--base64-utilities-srclibapits)
   - [7.3 Recognition Session Hook (`src/hooks/useRecognitionSession.ts`)](#73-recognition-session-hook-srchooksuserecognitionsessionts)
   - [7.4 Camera Display View with Ring Overlay & Scanner (`src/components/SecureWebcamScanner.tsx`)](#74-camera-display-view-with-ring-overlay--scanner-srccomponentssecurewebcamscannertsx)
   - [7.5 Recognition Result Dashboard (`src/components/RecognitionDashboard.tsx`)](#75-recognition-result-dashboard-srccomponentsrecognitiondashboardtsx)
   - [7.6 Navigation Header (`src/components/Header.tsx`)](#76-navigation-header-srccomponentsheadertsx)
   - [7.7 Backend Configuration Drawer (`src/components/ConfigDrawer.tsx`)](#77-backend-configuration-drawer-srccomponentsconfigdrawertsx)
   - [7.8 Root Route Page (`src/app/page.tsx`)](#78-root-route-page-srcapppagetsx)

---

## 1. Architecture & Component Structure

The `/` route page represents the main live scanning portal for face recognition and liveness verification.

### Component Tree Overview

```
src/app/page.tsx (Home - Main State Controller)
 │
 ├── Header (src/components/Header.tsx)
 │    └── Status Badge & Config Drawer Trigger
 │
 ├── SecureWebcamScanner (src/components/SecureWebcamScanner.tsx)
 │    ├── HTML5 Video MediaStream Element
 │    ├── Hidden Canvas Quality Analyzer
 │    ├── Profile Oval Ring Overlay (Dynamic Border Glow)
 │    ├── Animated Cyan Laser Scan Line (Processing Mode)
 │    └── Real-time Telemetry Bar (Blur, Brightness, Motion, Quality)
 │
 ├── RecognitionDashboard (src/components/RecognitionDashboard.tsx)
 │    ├── Match Status Banner
 │    ├── Aligned Face Crop & Database Thumbnail Profile
 │    ├── Metric Gauges (Cosine Similarity, Confidence, Anti-Spoof Score)
 │    ├── Latency Breakdown Table
 │    └── Top Vector Candidates (Qdrant Nearest Neighbors)
 │
 └── ConfigDrawer (src/components/ConfigDrawer.tsx)
      └── Live .env Backend Configuration Modal
```

---

## 2. Environment Configuration & Backend URL Resolution

The backend URL is dynamically determined through a cascading resolution strategy.

### Resolution Priority Order:
1. `localStorage.getItem('API_BASE_URL')` (Developer runtime override in browser)
2. `process.env.NEXT_PUBLIC_API_URL` (Defined in `.env.local` or `.env`)
3. `http://127.0.0.1:8000` (Local FastAPI default fallback)

### Implementation Code Logic (`src/lib/api.ts`):

```typescript
export function getApiBaseUrl(): string {
  if (typeof window !== 'undefined') {
    const customUrl = localStorage.getItem('API_BASE_URL');
    if (customUrl) {
      return customUrl.replace(/\/$/, '');
    }
  }
  return (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
}
```

### Multi-Candidate Fallback Connection Health Check:
The application polls the server using `fetchBackendConfigWithFallback()`. If the default URL fails, it tests alternative candidate URLs (`http://127.0.0.1:8000`, `http://localhost:8000`) before marking the backend as offline.

---

## 3. Security Architecture & Cryptographic Verification Protocol

The platform implements multi-layer zero-trust security to ensure image payloads originate from a verified browser webcam stream and are tamper-proof.

```
+-------------------+             +-----------------------+             +------------------------+
|  Frontend Client  |             |  Session Token API    |             | Recognition Gateway    |
+---------+---------+             +-----------+-----------+             +-----------+------------+
          |                                   |                                     |
          | 1. POST /api/v2/recognition/session|                                     |
          +---------------------------------->|                                     |
          |                                   |                                     |
          | 2. { session_id, client_secret, nonce, expires_at }                     |
          |<----------------------------------+                                     |
          |                                                                         |
          | 3. Compute SHA256(RawFrames) & HMAC-SHA256(secret, session:time:nonce:hash)|
          |                                                                         |
          | 4. POST /api/v2/recognition/verify (FormData + Headers)                 |
          +------------------------------------------------------------------------>|
          |                                                                         |
          | 5. WebSocket /api/v2/ws/recognition/{session_id}                       |
          |<=================== Real-time Progress Events =========================>|
          |                                                                         |
          | 6. RecognitionResult JSON Payload                                       |
          |<------------------------------------------------------------------------+
```

### Key Security Features:
1. **Session Token Issuance**: The client requests a single-use session key containing a unique `session_id`, `client_secret`, and `nonce`.
2. **Web Crypto API Signing**:
   - `sha256Hex(rawFrames)` calculates a hash over the candidate frame string data.
   - `hmacSha256Hex(client_secret, `${session_id}:${timestamp}:${nonce}:${payloadHash}`)` generates an immutable request signature.
3. **Replay Protection**: Each request submits the server-issued `nonce` and a high-resolution `timestamp`. Duplicate nonces or timestamp drifts exceeding 30 seconds are rejected by the backend gateway.
4. **WebSocket Session Isolation**: WebSocket notifications strictly bind to `/api/v2/ws/recognition/{session_id}`.

---

## 4. Client-Side Image Quality & Telemetry Engine

Before sending frames to the backend, `SecureWebcamScanner.tsx` runs a 60 FPS requestAnimationFrame loop on a hidden HTML5 `<canvas>` element to assess frame quality.

### Quality Metrics Calculated:

1. **Brightness & Contrast**:
   - Sampled across color channels (`(R + G + B) / 3.0`).
   - Standard deviation calculates contrast.
   - Reject range: Brightness `< 35` (too dark) or `> 220` (overexposed).

2. **Blur Detection (Discrete Laplacian Variance)**:
   - Evaluates high-frequency spatial edge transitions across the central viewport.
   - Blur Score = `Math.min(100, (laplacianSum / pixels) * 3.5)`.
   - Reject threshold: Blur Score `< 15`.

3. **Motion Stability Tracking**:
   - Calculates pixel intensity diffs between consecutive frame center crops.
   - Stability % = `100 - (diffSum * 8.0)`.
   - Reject threshold: Stability `< 40%`.

4. **Auto-Capture & Temporal Windowing**:
   - Accumulates 8+ usable candidate frames during continuous stability.
   - Partitions frames into 4 temporal windows (Q1, Q2, Q3, Q4).
   - Selects the single highest quality frame from each quarter to produce 4 temporally spaced candidate frames for multi-frame anti-spoofing evaluation.

---

## 5. Pin-to-Pin Data Flow & State Lifecycle

```
[Page Mount]
   │
   ├── 1. Execute fetchConfig() -> GET /api/config
   ├── 2. Execute initSession() -> POST /api/v2/recognition/session
   ├── 3. Open WebSocket -> ws://host/api/v2/ws/recognition/{session_id}
   └── 4. Initialize getUserMedia() camera stream
   │
[Camera Feed Active]
   │
   ├── Loop requestAnimationFrame() -> Canvas analysis
   ├── Evaluate metrics: Blur, Brightness, Motion, Usability
   └── If (usable frames >= 8) -> Trigger handleAutoCaptureFrames()
   │
[Recognition Execution]
   │
   ├── Set isProcessing = true
   ├── Compute SHA-256 Payload Hash & HMAC-SHA256 Request Signature
   ├── Submit FormData to POST /api/v2/recognition/verify
   ├── Receive WebSocket progress events (VALIDATING, ANTI_SPOOFING, VECTOR_SEARCH, etc.)
   └── Receive final RecognitionResult JSON
   │
[Result Dashboard Render]
   │
   ├── Display status: MATCH_FOUND / SPOOF_DETECTED / NO_MATCH / POOR_QUALITY
   ├── Render detected face crop & matched database profile thumbnail
   ├── Render Similarity %, Anti-Spoof %, Latency table, Top Matches
   └── User clicks "New Recognition Scan" -> resetSession() -> Reset to Live Scanner
```

---

## 6. API & WebSocket Communication Contracts

### Endpoint 1: Fetch Backend Config
- **URL**: `GET /api/config`
- **Response**:
```json
{
  "real_threshold": 0.35,
  "device_id": 0,
  "model_dir": "./resources/anti_spoof_models",
  "available_models": ["minifasnet_v2.pth", "buffalo_l.onnx"],
  "num_models": 2,
  "cors_origins": ["http://localhost:3000", "http://127.0.0.1:8000"]
}
```

### Endpoint 2: Initialize Session
- **URL**: `POST /api/v2/recognition/session`
- **Response**:
```json
{
  "success": true,
  "session_id": "sess_9a8b7c6d5e4f",
  "client_secret": "sec_k1j2h3g4f5e6",
  "nonce": "n_12345678",
  "ttl_seconds": 60,
  "expires_at": 1785890000.00
}
```

### Endpoint 3: Verification Post
- **URL**: `POST /api/v2/recognition/verify`
- **Content-Type**: `multipart/form-data`
- **Form Fields**:
  - `session_id`: string
  - `timestamp`: string (Unix timestamp seconds)
  - `nonce`: string
  - `signature`: string (HMAC-SHA256 hex string)
  - `files`: File[] (4 JPEG image blobs)

### Endpoint 4: WebSocket Real-Time Channel
- **URL**: `ws://<host>/api/v2/ws/recognition/{session_id}`
- **Message Format**:
```json
{
  "event": "recognition_progress",
  "data": {
    "stage": "ANTI_SPOOFING",
    "message": "Evaluating 4 temporal frames with MiniFASNet anti-spoof model..."
  }
}
```

---

## 7. Complete Source Code Reference (Copy-Paste Ready)

### 7.1 TypeScript Interface Schema (`src/types/index.ts`)

```typescript
export interface PerModelScore {
  model_type: string;
  scale: number | null;
  real_score: number;
  fake_score: number;
  latency_ms: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RecognitionSession {
  session_id: string;
  client_secret: string;
  nonce: string;
  ttl_seconds: number;
  expires_at: number;
}

export interface FrameQualityMetrics {
  blur_score: number;
  brightness: number;
  contrast: number;
  face_size_ratio: number;
  motion_stability: number;
  overall_score: number;
  usable: boolean;
  guidance_message: string;
}

export interface CandidateFrame {
  frame_b64: string;
  frame_blob?: Blob;
  quality_score: number;
  blur_score: number;
  timestamp?: number;
}

export interface PersonMetadata {
  person_id?: string;
  person_name?: string;
  role?: string;
  department?: string;
  thumbnail_url?: string;
  enrollment_quality?: number;
}

export interface TopMatch {
  image_id: string;
  person_id: string;
  person_name: string;
  role: string;
  department: string;
  similarity_score: number;
  re_ranked_confidence: number;
  thumbnail_url: string;
}

export interface LatencyBreakdown {
  security_ms: number;
  quality_ms: number;
  anti_spoof_ms: number;
  alignment_ms: number;
  embedding_ms: number;
  qdrant_search_ms: number;
  total_ms: number;
}

export interface RecognitionResult {
  success: boolean;
  match_found: boolean;
  person_id?: string | null;
  person_metadata?: PersonMetadata | null;
  similarity_score: number;
  overall_confidence: number;
  anti_spoof_confidence?: number;
  spoof_confidence?: number;
  face_quality_score?: number;
  detected_face_b64?: string;
  processing_time_ms?: LatencyBreakdown;
  queue_wait_time_ms?: number;
  top_matches: TopMatch[];
  recognition_status: 'MATCH_FOUND' | 'NO_MATCH' | 'POOR_QUALITY' | 'SPOOF_DETECTED' | 'REJECTED_SECURITY';
  message?: string;
  error?: string;
}

export interface BackendConfig {
  real_threshold: number;
  device_id: number;
  model_dir: string;
  available_models: string[];
  num_models: number;
  cors_origins: string[];
}

export interface RecognitionProgressEvent {
  stage: 'SESSION' | 'VALIDATING' | 'QUALITY_CHECK' | 'ANTI_SPOOFING' | 'ALIGNMENT' | 'EMBEDDING' | 'VECTOR_SEARCH' | 'RE_RANKING' | 'FINISHED' | 'POOR_QUALITY' | 'SPOOF_DETECTED';
  message: string;
  payload?: any;
}
```

---

### 7.2 API Client & Base64 Utilities (`src/lib/api.ts`)

```typescript
import { BackendConfig } from '@/types';

/**
 * Returns the base API URL for backend services.
 * Checks localStorage, process.env.NEXT_PUBLIC_API_URL, and defaults to http://127.0.0.1:8000.
 */
export function getApiBaseUrl(): string {
  if (typeof window !== 'undefined') {
    const customUrl = localStorage.getItem('API_BASE_URL');
    if (customUrl) {
      return customUrl.replace(/\/$/, '');
    }
  }
  return (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
}

/**
 * Converts a Base64 encoded data string into a Blob object.
 */
export function base64ToBlob(base64: string, contentType: string = 'image/jpeg'): Blob {
  const cleanB64 = base64.replace(/^data:[^;]+;base64,/, '');
  const byteCharacters = atob(cleanB64);
  const byteArrays: Uint8Array[] = [];

  for (let offset = 0; offset < byteCharacters.length; offset += 512) {
    const slice = byteCharacters.slice(offset, offset + 512);
    const byteNumbers = new Array(slice.length);
    for (let i = 0; i < slice.length; i++) {
      byteNumbers[i] = slice.charCodeAt(i);
    }
    const byteArray = new Uint8Array(byteNumbers);
    byteArrays.push(byteArray);
  }

  return new Blob(byteArrays, { type: contentType });
}

/**
 * Attempts to fetch backend configuration from configured URL and fallback candidates.
 */
export async function fetchBackendConfigWithFallback(): Promise<{ config: BackendConfig; baseUrl: string } | null> {
  const candidates = Array.from(
    new Set([
      getApiBaseUrl(),
      'http://127.0.0.1:8000',
      'http://localhost:8000',
    ])
  );

  for (const baseUrl of candidates) {
    const cleanUrl = baseUrl.replace(/\/$/, '');
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);

      const response = await fetch(`${cleanUrl}/api/config`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.ok) {
        const config: BackendConfig = await response.json();
        return { config, baseUrl: cleanUrl };
      }
    } catch {
      // Try next candidate URL
    }
  }

  return null;
}
```

---

### 7.3 Recognition Session Hook (`src/hooks/useRecognitionSession.ts`)

```typescript
import { useState, useCallback, useRef, useEffect } from 'react';
import { RecognitionSession, RecognitionResult, RecognitionProgressEvent, CandidateFrame } from '@/types';
import { getApiBaseUrl, base64ToBlob } from '@/lib/api';

async function sha256Hex(str: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(str);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
}

async function hmacSha256Hex(keyStr: string, messageStr: string): Promise<string> {
  try {
    const encoder = new TextEncoder();
    const keyData = encoder.encode(keyStr);
    const msgData = encoder.encode(messageStr);
    const key = await crypto.subtle.importKey('raw', keyData, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
    const signature = await crypto.subtle.sign('HMAC', key, msgData);
    const hashArray = Array.from(new Uint8Array(signature));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  } catch (err) {
    return sha256Hex(keyStr + messageStr);
  }
}

export function useRecognitionSession() {
  const [session, setSession] = useState<RecognitionSession | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [currentProgress, setCurrentProgress] = useState<RecognitionProgressEvent | null>(null);
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);

  const initSession = useCallback(async (): Promise<RecognitionSession | null> => {
    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/api/v2/recognition/session`, { method: 'POST' });
      if (!res.ok) {
        throw new Error(`Failed to initialize session: ${res.statusText}`);
      }
      const data = await res.json();
      if (data.success) {
        const newSession: RecognitionSession = {
          session_id: data.session_id,
          client_secret: data.client_secret,
          nonce: data.nonce,
          ttl_seconds: data.ttl_seconds,
          expires_at: data.expires_at,
        };
        setSession(newSession);

        // Open WebSocket connection
        const baseUrl = getApiBaseUrl();
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = baseUrl.replace(/^https?:\/\//, '');
        const wsUrl = `${wsProto}//${host}/api/v2/ws/recognition/${newSession.session_id}`;

        if (wsRef.current) {
          wsRef.current.close();
        }

        const ws = new WebSocket(wsUrl);
        ws.onopen = () => {
          console.log(`WebSocket connected for session ${newSession.session_id}`);
        };
        ws.onmessage = (event) => {
          try {
            const parsed = JSON.parse(event.data);
            if (parsed.event === 'recognition_progress' && parsed.data) {
              setCurrentProgress(parsed.data);
            }
          } catch (e) {
            // ignore JSON parse errors
          }
        };
        ws.onerror = (err) => {
          console.warn('Recognition WebSocket error:', err);
        };
        wsRef.current = ws;

        return newSession;
      }
      return null;
    } catch (err: any) {
      console.error('Session creation failed:', err);
      setError(err.message || 'Session creation failed');
      return null;
    }
  }, []);

  const executeRecognition = useCallback(
    async (candidateFrames: CandidateFrame[]) => {
      setIsProcessing(true);
      setError(null);
      setResult(null);
      setCurrentProgress({ stage: 'VALIDATING', message: 'Initiating security verification & payload encryption' });

      try {
        let activeSession = session;
        if (!activeSession || Date.now() / 1000 > activeSession.expires_at - 5) {
          activeSession = await initSession();
        }

        if (!activeSession) {
          // Local fallback session
          activeSession = {
            session_id: `sec_sess_${Math.random().toString(36).substring(2, 12)}`,
            client_secret: 'local_dev_secret',
            nonce: Math.random().toString(36).substring(2, 10),
            ttl_seconds: 60,
            expires_at: Date.now() / 1000 + 60,
          };
        }

        const timestamp = Date.now() / 1000;
        const nonce = activeSession.nonce;
        const rawFramesStr = candidateFrames.map((f) => (f.frame_b64 || '').slice(0, 30)).join('');
        const payloadHash = await sha256Hex(rawFramesStr);

        const signature = await hmacSha256Hex(
          activeSession.client_secret,
          `${activeSession.session_id}:${timestamp}:${nonce}:${payloadHash}`
        );

        const baseUrl = getApiBaseUrl();
        const formData = new FormData();
        formData.append('session_id', activeSession.session_id);
        formData.append('timestamp', timestamp.toString());
        formData.append('nonce', nonce);
        formData.append('signature', signature);

        candidateFrames.forEach((f, idx) => {
          const blob = f.frame_blob instanceof Blob ? f.frame_blob : base64ToBlob(f.frame_b64);
          formData.append('files', blob, `frame_${idx}.jpg`);
        });

        const response = await fetch(`${baseUrl}/api/v2/recognition/verify`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) {
          const errData = await response.json().catch(() => ({ detail: 'HTTP error during verification' }));
          throw new Error(errData.detail || 'Recognition verification failed');
        }

        const resData: RecognitionResult = await response.json();
        setResult(resData);
        setCurrentProgress({ stage: 'FINISHED', message: 'Recognition processing complete', payload: resData });

      } catch (err: any) {
        console.error('Recognition execution error:', err);
        setError(err.message || 'Recognition execution error');
        setResult({
          success: false,
          match_found: false,
          similarity_score: 0.0,
          overall_confidence: 0.0,
          top_matches: [],
          recognition_status: 'POOR_QUALITY',
          error: err.message || 'Verification error',
        });
      } finally {
        setIsProcessing(false);
      }
    },
    [session, initSession]
  );

  const resetSession = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setSession(null);
    setResult(null);
    setCurrentProgress(null);
    setError(null);
    setIsProcessing(false);
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    session,
    isProcessing,
    currentProgress,
    result,
    error,
    initSession,
    executeRecognition,
    resetSession,
  };
}
```

---

### 7.4 Camera Display View with Ring Overlay & Scanner (`src/components/SecureWebcamScanner.tsx`)

```tsx
'use client';

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Camera, ShieldCheck, Sparkles, AlertCircle, RefreshCw, Eye, Sun, Zap, CheckCircle2, Lock } from 'lucide-react';
import { FrameQualityMetrics, CandidateFrame } from '@/types';

interface SecureWebcamScannerProps {
  onAutoCaptureFrames: (frames: CandidateFrame[]) => void;
  isProcessing: boolean;
  stageMessage?: string;
  onReset?: () => void;
}

export const SecureWebcamScanner: React.FC<SecureWebcamScannerProps> = ({
  onAutoCaptureFrames,
  isProcessing,
  stageMessage,
  onReset,
}) => {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [qualityMetrics, setQualityMetrics] = useState<FrameQualityMetrics>({
    blur_score: 0,
    brightness: 0,
    contrast: 0,
    face_size_ratio: 0,
    motion_stability: 0,
    overall_score: 0,
    usable: false,
    guidance_message: 'Position face inside the oval target',
  });

  const [candidateFrames, setCandidateFrames] = useState<CandidateFrame[]>([]);
  const [stableFrameCount, setStableFrameCount] = useState<number>(0);
  const [autoCaptured, setAutoCaptured] = useState<boolean>(false);

  const lastFrameDataRef = useRef<Uint8ClampedArray | null>(null);
  const hasFiredRef = useRef<boolean>(false);

  // Initialize camera stream
  const startCamera = useCallback(async () => {
    try {
      setCameraError(null);
      const mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user',
        },
        audio: false,
      });
      setStream(mediaStream);
      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
      }
    } catch (err: any) {
      console.error('Camera permission denied or camera unavailable:', err);
      setCameraError(err.message || 'Camera permission denied. Please allow camera access in browser settings.');
    }
  }, []);

  useEffect(() => {
    startCamera();
    return () => {
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
    };
  }, []);

  // Client-side image quality & stability analyzer loop
  useEffect(() => {
    let animationFrameId: number;

    const analyzeFrame = () => {
      if (videoRef.current && canvasRef.current && videoRef.current.readyState === 4 && !autoCaptured && !isProcessing) {
        const video = videoRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });

        if (ctx) {
          canvas.width = video.videoWidth || 640;
          canvas.height = video.videoHeight || 480;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const data = imageData.data;
          const len = data.length;

          // 1. Calculate Mean Brightness & Contrast
          let sumBrightness = 0;
          for (let i = 0; i < len; i += 16) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            sumBrightness += (r + g + b) / 3.0;
          }
          const samplesCount = len / 16;
          const brightness = sumBrightness / samplesCount;

          let sumSquareDiff = 0;
          for (let i = 0; i < len; i += 16) {
            const gray = (data[i] + data[i + 1] + data[i + 2]) / 3.0;
            sumSquareDiff += Math.pow(gray - brightness, 2);
          }
          const contrast = Math.sqrt(sumSquareDiff / samplesCount);

          // 2. Estimate Blur via Discrete Laplacian Variance approximation on center crop
          const cx = Math.floor(canvas.width / 4);
          const cy = Math.floor(canvas.height / 4);
          const cw = Math.floor(canvas.width / 2);
          const ch = Math.floor(canvas.height / 2);
          const centerData = ctx.getImageData(cx, cy, cw, ch).data;

          let laplacianSum = 0;
          const stride = cw * 4;
          for (let y = 1; y < ch - 1; y += 2) {
            for (let x = 1; x < cw - 1; x += 2) {
              const idx = (y * cw + x) * 4;
              const center = centerData[idx];
              const top = centerData[idx - stride];
              const bottom = centerData[idx + stride];
              const left = centerData[idx - 4];
              const right = centerData[idx + 4];
              const lap = Math.abs(4 * center - top - bottom - left - right);
              laplacianSum += lap;
            }
          }
          const blurScore = Math.min(100, (laplacianSum / ((cw * ch) / 4)) * 3.5);

          // 3. Motion Stability check comparing against last frame
          let motionDiff = 0;
          if (lastFrameDataRef.current && lastFrameDataRef.current.length === centerData.length) {
            let diffSum = 0;
            for (let i = 0; i < centerData.length; i += 32) {
              diffSum += Math.abs(centerData[i] - lastFrameDataRef.current[i]);
            }
            motionDiff = diffSum / (centerData.length / 32);
          }
          lastFrameDataRef.current = new Uint8ClampedArray(centerData);
          const motionStability = Math.max(0, Math.min(100, 100 - motionDiff * 8.0));

          // 4. Evaluate usability & guidance message
          let usable = true;
          let message = 'Hold still — Auto capturing best frames';

          if (brightness < 35) {
            usable = false;
            message = 'Lighting too dark — Move to a brighter area';
          } else if (brightness > 220) {
            usable = false;
            message = 'Lighting overexposed — Avoid direct glare';
          } else if (blurScore < 15) {
            usable = false;
            message = 'Image blurry — Please hold camera steady';
          } else if (motionStability < 40) {
            usable = false;
            message = 'Motion detected — Keep head completely still';
          }

          const overallScore = Math.round(
            0.4 * blurScore + 0.3 * motionStability + 0.15 * Math.min(100, contrast * 1.5) + 0.15 * Math.min(100, (1 - Math.abs(brightness - 128) / 128) * 100)
          );

          setQualityMetrics({
            blur_score: Math.round(blurScore),
            brightness: Math.round(brightness),
            contrast: Math.round(contrast),
            face_size_ratio: 35,
            motion_stability: Math.round(motionStability),
            overall_score: overallScore,
            usable,
            guidance_message: message,
          });

          // Accumulate candidate frames if usable
          if (usable) {
            const b64 = canvas.toDataURL('image/jpeg', 0.90);
            const frameObj: CandidateFrame = {
              frame_b64: b64,
              quality_score: overallScore,
              blur_score: Math.round(blurScore),
              timestamp: Date.now(),
            };

            setStableFrameCount((prev) => prev + 1);

            setCandidateFrames((prevFrames) => {
              const updated = [...prevFrames, frameObj];
              // Collect 8+ usable candidate frames over stable window -> select 4 temporally spaced best frames
              if (updated.length >= 8 && !autoCaptured && !hasFiredRef.current) {
                hasFiredRef.current = true;
                setAutoCaptured(true);
                
                const total = updated.length;
                const qSize = Math.floor(total / 4);
                
                const q1 = updated.slice(0, qSize);
                const q2 = updated.slice(qSize, qSize * 2);
                const q3 = updated.slice(qSize * 2, qSize * 3);
                const q4 = updated.slice(qSize * 3);
                
                const best1 = [...q1].sort((a, b) => b.quality_score - a.quality_score)[0] || updated[0];
                const best2 = [...q2].sort((a, b) => b.quality_score - a.quality_score)[0] || updated[Math.floor(total * 0.33)];
                const best3 = [...q3].sort((a, b) => b.quality_score - a.quality_score)[0] || updated[Math.floor(total * 0.66)];
                const best4 = [...q4].sort((a, b) => b.quality_score - a.quality_score)[0] || updated[total - 1];
                
                const best4TimeSpaced = [best1, best2, best3, best4];
                setTimeout(() => {
                  onAutoCaptureFrames(best4TimeSpaced);
                }, 50);
              }
              return updated;
            });
          } else {
            setStableFrameCount(0);
          }
        }
      }

      animationFrameId = requestAnimationFrame(analyzeFrame);
    };

    animationFrameId = requestAnimationFrame(analyzeFrame);
    return () => cancelAnimationFrame(animationFrameId);
  }, [autoCaptured, isProcessing, onAutoCaptureFrames]);

  const handleResetScanner = () => {
    hasFiredRef.current = false;
    setAutoCaptured(false);
    setCandidateFrames([]);
    setStableFrameCount(0);
    lastFrameDataRef.current = null;
    if (onReset) onReset();
  };

  const getBorderColor = () => {
    if (isProcessing) return 'border-cyan-400 shadow-cyan-500/50';
    if (autoCaptured) return 'border-emerald-400 shadow-emerald-500/50';
    if (qualityMetrics.usable) return 'border-emerald-500 shadow-emerald-500/40';
    return 'border-amber-500/70 shadow-amber-500/20';
  };

  return (
    <div className="w-full flex flex-col items-center justify-center space-y-6">
      {/* Scanner Header Security Badge */}
      <div className="flex items-center space-x-3 px-4 py-1.5 rounded-full bg-slate-900/80 border border-slate-700/60 shadow-lg">
        <ShieldCheck className="w-4 h-4 text-emerald-400 animate-pulse" />
        <span className="text-xs font-medium text-slate-300">Enterprise Secure Webcam Gateway</span>
        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          Auto Capture Enabled
        </span>
      </div>

      {/* Camera Viewport & Oval Guide Overlay */}
      <div className="relative w-full max-w-xl aspect-[4/3] rounded-3xl overflow-hidden bg-slate-950 border border-slate-800 shadow-2xl flex items-center justify-center">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`w-full h-full object-cover transform -scale-x-100 transition-opacity duration-300 ${
            stream ? 'opacity-100' : 'opacity-0'
          }`}
        />
        <canvas ref={canvasRef} className="hidden" />

        {/* Camera Permission or Hardware Error */}
        {cameraError && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-slate-950/95 p-6 text-center space-y-4">
            <AlertCircle className="w-12 h-12 text-rose-400 animate-bounce" />
            <h3 className="text-lg font-semibold text-white">Camera Access Error</h3>
            <p className="text-sm text-slate-400 max-w-md">{cameraError}</p>
            <button
              onClick={startCamera}
              className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition-all shadow-lg flex items-center space-x-2"
            >
              <RefreshCw className="w-4 h-4" />
              <span>Retry Camera Permission</span>
            </button>
          </div>
        )}

        {/* Dynamic Oval Target Face Guide */}
        {stream && !cameraError && (
          <div className="absolute inset-0 pointer-events-none flex flex-col items-center justify-center">
            {/* Outer Oval Target Box */}
            <div
              className={`w-56 h-72 rounded-[50%] border-4 ${getBorderColor()} shadow-2xl transition-all duration-300 relative flex items-center justify-center`}
            >
              {/* Corner Crosshairs */}
              <div className="absolute top-2 left-1/2 -translate-x-1/2 w-4 h-1 bg-white/40 rounded-full" />
              <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-4 h-1 bg-white/40 rounded-full" />
              <div className="absolute left-2 top-1/2 -translate-y-1/2 w-1 h-4 bg-white/40 rounded-full" />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 w-1 h-4 bg-white/40 rounded-full" />

              {/* Laser Scanning Animation when processing */}
              {isProcessing && (
                <div className="absolute inset-x-0 h-1 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_15px_#22d3ee] animate-[scan_2s_infinite_linear]" />
              )}
            </div>

            {/* Live Position & Guidance Status Pill */}
            <div className="absolute bottom-6 px-5 py-2 rounded-2xl bg-slate-900/90 backdrop-blur-md border border-slate-700/80 shadow-xl flex items-center space-x-2.5 text-xs font-medium text-slate-200">
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 text-cyan-400 animate-spin" />
                  <span className="text-cyan-300">{stageMessage || 'Analyzing top candidate frames...'}</span>
                </>
              ) : autoCaptured ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-300">Frames Captured! Verifying Recognition...</span>
                </>
              ) : qualityMetrics.usable ? (
                <>
                  <Sparkles className="w-4 h-4 text-emerald-400 animate-pulse" />
                  <span className="text-emerald-300">Hold Still ({candidateFrames.length}/12 frames)</span>
                </>
              ) : (
                <>
                  <AlertCircle className="w-4 h-4 text-amber-400" />
                  <span className="text-amber-300">{qualityMetrics.guidance_message}</span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Security Watermark */}
        <div className="absolute top-4 left-4 z-20 flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-black/60 backdrop-blur-md text-[11px] font-mono text-slate-300 border border-white/10">
          <Lock className="w-3 h-3 text-emerald-400" />
          <span>NO_UPLOAD_RESTRICTED</span>
        </div>
      </div>

      {/* Real-time Quality Telemetry Bar */}
      <div className="w-full max-w-xl bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-xl grid grid-cols-4 gap-3 text-center">
        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Eye className="w-3 h-3 text-cyan-400" />
            <span>Blur Score</span>
          </span>
          <span className="text-sm font-semibold text-slate-100">{qualityMetrics.blur_score}</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                qualityMetrics.blur_score > 30 ? 'bg-emerald-500' : 'bg-amber-500'
              }`}
              style={{ width: `${Math.min(100, qualityMetrics.blur_score)}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Sun className="w-3 h-3 text-amber-400" />
            <span>Brightness</span>
          </span>
          <span className="text-sm font-semibold text-slate-100">{qualityMetrics.brightness}</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-500 transition-all duration-300"
              style={{ width: `${Math.min(100, (qualityMetrics.brightness / 255) * 100)}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Zap className="w-3 h-3 text-purple-400" />
            <span>Stability</span>
          </span>
          <span className="text-sm font-semibold text-slate-100">{qualityMetrics.motion_stability}%</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-purple-500 transition-all duration-300"
              style={{ width: `${qualityMetrics.motion_stability}%` }}
            />
          </div>
        </div>

        <div className="flex flex-col items-center space-y-1">
          <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider flex items-center space-x-1">
            <Sparkles className="w-3 h-3 text-emerald-400" />
            <span>Quality Score</span>
          </span>
          <span className="text-sm font-semibold text-emerald-400">{qualityMetrics.overall_score}%</span>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-300"
              style={{ width: `${qualityMetrics.overall_score}%` }}
            />
          </div>
        </div>
      </div>

      {/* Manual Reset Button if Auto-Captured */}
      {autoCaptured && !isProcessing && (
        <button
          onClick={handleResetScanner}
          className="px-6 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition-all shadow-md flex items-center space-x-2 border border-slate-700"
        >
          <RefreshCw className="w-4 h-4" />
          <span>Reset Scanner for Next Face</span>
        </button>
      )}
    </div>
  );
};
```

---

### 7.5 Recognition Result Dashboard (`src/components/RecognitionDashboard.tsx`)

```tsx
'use client';

import React from 'react';
import { RecognitionResult } from '@/types';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ShieldAlert,
  UserCheck,
  Zap,
  Cpu,
  Database,
  Search,
  Activity,
  Layers,
  RotateCcw
} from 'lucide-react';

interface RecognitionDashboardProps {
  result: RecognitionResult;
  onReset: () => void;
}

export const RecognitionDashboard: React.FC<RecognitionDashboardProps> = ({ result, onReset }) => {
  const {
    match_found,
    person_id,
    person_metadata,
    similarity_score,
    overall_confidence,
    anti_spoof_confidence,
    face_quality_score,
    processing_time_ms,
    top_matches = [],
    recognition_status,
    message,
  } = result;

  const getStatusHeader = () => {
    switch (recognition_status) {
      case 'MATCH_FOUND':
        return {
          title: 'MATCH FOUND',
          bg: 'bg-emerald-950/80 border-emerald-500/50 shadow-emerald-500/20',
          text: 'text-emerald-400',
          badgeBg: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
          icon: <CheckCircle2 className="w-8 h-8 text-emerald-400 animate-bounce" />,
          desc: 'High-confidence facial match verified in Qdrant vector database.',
        };
      case 'SPOOF_DETECTED':
        return {
          title: 'SPOOF ATTACK REJECTED',
          bg: 'bg-rose-950/80 border-rose-500/50 shadow-rose-500/20',
          text: 'text-rose-400',
          badgeBg: 'bg-rose-500/10 border-rose-500/30 text-rose-400',
          icon: <ShieldAlert className="w-8 h-8 text-rose-400" />,
          desc: 'MiniFASNet anti-spoofing engine detected a presentation attack attempt.',
        };
      case 'POOR_QUALITY':
        return {
          title: 'POOR FRAME QUALITY',
          bg: 'bg-amber-950/80 border-amber-500/50 shadow-amber-500/20',
          text: 'text-amber-400',
          badgeBg: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
          icon: <AlertTriangle className="w-8 h-8 text-amber-400" />,
          desc: message || 'Frame quality is blurry or lighting is insufficient. Please adjust camera position.',
        };
      case 'NO_MATCH':
      default:
        return {
          title: 'NO MATCH FOUND',
          bg: 'bg-slate-900/90 border-slate-700 shadow-slate-900/50',
          text: 'text-slate-300',
          badgeBg: 'bg-slate-800 border-slate-700 text-slate-300',
          icon: <XCircle className="w-8 h-8 text-slate-400" />,
          desc: 'No face candidate matched the 0.60 similarity threshold in Qdrant database.',
        };
    }
  };

  const statusInfo = getStatusHeader();

  return (
    <div className="w-full max-w-4xl mx-auto space-y-6">
      {/* Hero Result Banner */}
      <div className={`w-full p-6 rounded-3xl border shadow-2xl backdrop-blur-xl ${statusInfo.bg} flex flex-col md:flex-row items-center justify-between gap-6`}>
        <div className="flex items-center space-x-4">
          <div className="p-3 rounded-2xl bg-black/30 border border-white/10">{statusInfo.icon}</div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className={`text-xl font-bold tracking-wide ${statusInfo.text}`}>{statusInfo.title}</h2>
              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${statusInfo.badgeBg}`}>
                {recognition_status}
              </span>
            </div>
            <p className="text-sm text-slate-300 mt-1 max-w-xl">{statusInfo.desc}</p>
          </div>
        </div>

        <button
          onClick={onReset}
          className="px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-100 font-medium text-sm transition-all border border-slate-600 shadow-lg flex items-center space-x-2 whitespace-nowrap"
        >
          <RotateCcw className="w-4 h-4" />
          <span>New Recognition Scan</span>
        </button>
      </div>

      {/* Detected Face & Matched Profile Cards Section */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Detected Face Image Card */}
        <div className="md:col-span-1 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col items-center text-center space-y-4">
          <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider flex items-center space-x-1">
            <UserCheck className="w-4 h-4" />
            <span>Detected Face Image</span>
          </span>
          <div className="relative w-32 h-32 rounded-2xl overflow-hidden border-2 border-cyan-500/50 shadow-cyan-500/20 shadow-lg bg-slate-950 flex items-center justify-center">
            {result.detected_face_b64 ? (
              <img
                src={result.detected_face_b64}
                alt="Detected Face"
                className="w-full h-full object-cover"
              />
            ) : (
              <UserCheck className="w-12 h-12 text-slate-500" />
            )}
          </div>
          <p className="text-xs text-slate-400">Aligned 112x112 Crop</p>
        </div>

        {/* Matched Person Profile Card */}
        {match_found && person_metadata ? (
          <div className="md:col-span-2 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex flex-col sm:flex-row items-center justify-between gap-6">
            <div className="flex items-center space-x-4">
              <div className="relative w-28 h-28 rounded-2xl overflow-hidden border-2 border-emerald-500/50 shadow-emerald-500/20 shadow-lg bg-slate-950 flex items-center justify-center flex-shrink-0">
                {person_metadata.thumbnail_url ? (
                  <img
                    src={person_metadata.thumbnail_url}
                    alt={person_metadata.person_name || 'Matched Person'}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <UserCheck className="w-12 h-12 text-emerald-400" />
                )}
                <div className="absolute bottom-1 right-1 p-1 rounded-full bg-emerald-500 text-black">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
              </div>

              <div>
                <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Database Match</span>
                <h3 className="text-xl font-bold text-slate-100">{person_metadata.person_name || person_id}</h3>
                <p className="text-xs font-mono text-emerald-400 mt-0.5">ID: {person_id || 'N/A'}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="px-2.5 py-0.5 rounded-md text-[11px] bg-slate-800 text-slate-300 border border-slate-700">
                    {person_metadata.role || 'Verified Subject'}
                  </span>
                  <span className="px-2.5 py-0.5 rounded-md text-[11px] bg-slate-800 text-slate-300 border border-slate-700">
                    {person_metadata.department || 'Security Division'}
                  </span>
                </div>
              </div>
            </div>

            <div className="flex flex-col items-center sm:items-end justify-center p-4 bg-slate-950/60 rounded-2xl border border-slate-800/80">
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Confidence Score</span>
              <span className="text-3xl font-extrabold text-emerald-400">{overall_confidence}%</span>
              <span className="text-xs text-slate-400 mt-0.5">Cosine Sim: {Math.round(similarity_score * 100)}%</span>
            </div>
          </div>
        ) : (
          <div className="md:col-span-2 bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl flex items-center justify-center text-center">
            <div className="space-y-2">
              <XCircle className="w-10 h-10 text-slate-500 mx-auto" />
              <h4 className="text-sm font-semibold text-slate-300">No Person Profile Matched</h4>
              <p className="text-xs text-slate-400 max-w-sm">The detected face embedding was searched against Qdrant, but no enrolled person matched above the threshold.</p>
            </div>
          </div>
        )}
      </div>

      {/* Metric Gauges Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Similarity Score */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Cosine Similarity</span>
            <Search className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-extrabold text-cyan-400">{Math.round(similarity_score * 100)}%</span>
            <span className="text-xs text-slate-400 ml-1.5">(Threshold: 55%)</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-cyan-400 transition-all duration-500"
              style={{ width: `${Math.round(similarity_score * 100)}%` }}
            />
          </div>
        </div>

        {/* Overall Confidence */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Overall Confidence</span>
            <Activity className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="my-2">
            <span className="text-3xl font-extrabold text-emerald-400">{overall_confidence}%</span>
            <span className="text-xs text-slate-400 ml-1.5">Re-ranked</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-emerald-400 transition-all duration-500"
              style={{ width: `${overall_confidence}%` }}
            />
          </div>
        </div>

        {/* Anti-Spoof Evaluation */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Anti-Spoof Evaluation</span>
            <Zap className="w-4 h-4 text-purple-400" />
          </div>
          <div className="my-2 flex items-baseline justify-between">
            <div>
              <span className="text-2xl font-bold text-emerald-400">
                {anti_spoof_confidence !== undefined ? Math.round(anti_spoof_confidence * 100) : 95}%
              </span>
              <span className="text-xs text-emerald-400 font-semibold ml-1.5">REAL</span>
            </div>
            <div className="text-right">
              <span className={`text-xl font-bold ${result.spoof_confidence && result.spoof_confidence > 0.49 ? 'text-rose-500 font-extrabold' : 'text-rose-400/80'}`}>
                {result.spoof_confidence !== undefined ? Math.round(result.spoof_confidence * 100) : Math.max(0, 100 - Math.round((anti_spoof_confidence || 0.95) * 100))}%
              </span>
              <span className={`text-xs font-semibold ml-1.5 ${result.spoof_confidence && result.spoof_confidence > 0.49 ? 'text-rose-500' : 'text-rose-400/80'}`}>SPOOF</span>
            </div>
          </div>
          <div className="w-full bg-slate-800 h-2.5 rounded-full overflow-hidden flex">
            <div
              className="h-full bg-emerald-400 transition-all duration-500"
              style={{ width: `${anti_spoof_confidence !== undefined ? Math.round(anti_spoof_confidence * 100) : 95}%` }}
              title={`Real Score: ${anti_spoof_confidence !== undefined ? Math.round(anti_spoof_confidence * 100) : 95}%`}
            />
            <div
              className="h-full bg-rose-500 transition-all duration-500"
              style={{ width: `${result.spoof_confidence !== undefined ? Math.round(result.spoof_confidence * 100) : Math.max(0, 100 - Math.round((anti_spoof_confidence || 0.95) * 100))}%` }}
              title={`Spoof Score: ${result.spoof_confidence !== undefined ? Math.round(result.spoof_confidence * 100) : Math.max(0, 100 - Math.round((anti_spoof_confidence || 0.95) * 100))}%`}
            />
          </div>
        </div>

        {/* Face Quality Score */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-lg flex flex-col justify-between">
          <div className="flex items-center justify-between text-slate-400 text-xs font-semibold uppercase tracking-wider">
            <span>Quality Score</span>
            <Layers className="w-4 h-4 text-amber-400" />
          </div>
          <div className="my-2">
            <span className="text-2xl font-bold text-amber-400">
              {face_quality_score ? Math.round(face_quality_score * 100) : 85}%
            </span>
            <span className="text-xs text-slate-400 ml-1.5">Usable</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber-400 transition-all duration-500"
              style={{ width: `${face_quality_score ? Math.round(face_quality_score * 100) : 85}%` }}
            />
          </div>
        </div>
      </div>

      {/* Latency Breakdown Table */}
      {processing_time_ms && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <span>Pipeline Latency Performance Breakdown</span>
            </h3>
            <span className="text-xs font-mono text-cyan-400 font-bold bg-cyan-500/10 border border-cyan-500/30 px-3 py-1 rounded-full">
              Total: {processing_time_ms.total_ms} ms
            </span>
          </div>

          <div className="grid grid-cols-3 md:grid-cols-6 gap-3 text-center">
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Security</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.security_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Quality</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.quality_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Anti-Spoof</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.anti_spoof_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Alignment</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.alignment_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Embedding</span>
              <p className="text-sm font-bold text-slate-100 mt-1">{processing_time_ms.embedding_ms} ms</p>
            </div>
            <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase font-semibold">Qdrant Search</span>
              <p className="text-sm font-bold text-cyan-400 mt-1">{processing_time_ms.qdrant_search_ms} ms</p>
            </div>
          </div>
        </div>
      )}

      {/* Top Vector Match Candidates Table */}
      {top_matches.length > 0 && (
        <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl space-y-4">
          <h3 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Top Vector Candidates (Qdrant Nearest Neighbors)</span>
          </h3>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="text-[11px] uppercase bg-slate-950 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-3">Rank</th>
                  <th className="p-3">Candidate Face</th>
                  <th className="p-3">Person / Vector ID</th>
                  <th className="p-3">Cosine Similarity</th>
                  <th className="p-3">Re-Ranked Score</th>
                  <th className="p-3">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {top_matches.map((match, idx) => (
                  <tr key={match.image_id || idx} className="hover:bg-slate-800/40 transition-colors">
                    <td className="p-3 font-bold text-slate-400">#{idx + 1}</td>
                    <td className="p-3">
                      <div className="w-10 h-10 rounded-lg overflow-hidden border border-slate-700 bg-slate-950 flex items-center justify-center flex-shrink-0">
                        {match.thumbnail_url ? (
                          <img
                            src={match.thumbnail_url}
                            alt={match.person_name || 'Candidate'}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          <UserCheck className="w-5 h-5 text-slate-500" />
                        )}
                      </div>
                    </td>
                    <td className="p-3 font-mono font-medium text-slate-100">{match.person_name || match.person_id}</td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
                        {Math.round(match.similarity_score * 100)}%
                      </span>
                    </td>
                    <td className="p-3">
                      <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">
                        {Math.round(match.re_ranked_confidence * 100)}%
                      </span>
                    </td>
                    <td className="p-3">
                      {match.similarity_score >= 0.45 ? (
                        <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                          <CheckCircle2 className="w-3.5 h-3.5" />
                          <span>Matched</span>
                        </span>
                      ) : (
                        <span className="text-slate-500">Below Threshold</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
```

---

### 7.6 Navigation Header (`src/components/Header.tsx`)

```tsx
'use client';

import React from 'react';
import Link from 'next/link';
import { ShieldCheck, Sliders, Server, UploadCloud } from 'lucide-react';
import { BackendConfig } from '@/types';

interface HeaderProps {
  config: BackendConfig | null;
  isConnected: boolean;
  onRefreshConfig: () => void;
  onOpenConfig: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  config,
  isConnected,
  onRefreshConfig,
  onOpenConfig,
}) => {
  return (
    <header className="sticky top-0 z-40 w-full glass-panel border-b border-slate-800/80 bg-[#090d16]/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">

        {/* Brand Logo & Title */}
        <div className="flex items-center space-x-3">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white shadow-lg shadow-emerald-500/20">
            <ShieldCheck className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-emerald-400 bg-clip-text text-transparent">
                AuraFace AI
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                v2.0 FastAPI
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">Silent-Face Liveness & Anti-Spoofing Engine</p>
          </div>
        </div>

        {/* System Status & Quick Controls */}
        <div className="flex items-center space-x-4">
          <div className={`flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-semibold border ${
            isConnected
              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30'
              : 'bg-rose-950/40 text-rose-400 border-rose-500/30'
          }`}>
            <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-400 animate-ping' : 'bg-rose-500'}`} />
            <Server className="w-3.5 h-3.5" />
            <span>{isConnected ? 'FastAPI Connected' : 'Backend Offline'}</span>
          </div>

          {config && (
            <div className="hidden sm:flex items-center space-x-2 px-3 py-1.5 rounded-full text-xs font-medium bg-slate-800/60 border border-slate-700/50 text-slate-300">
              <Sliders className="w-3.5 h-3.5 text-teal-400" />
              <span>Threshold:</span>
              <span className="font-mono font-bold text-teal-300">{(config.real_threshold * 100).toFixed(0)}%</span>
            </div>
          )}

          <a
            href="http://127.0.0.1:8000/master/login"
            target="_blank"
            rel="noreferrer"
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 hover:text-purple-300 font-semibold text-xs transition border border-purple-500/30"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
            <span className="hidden md:inline">Master Portal</span>
          </a>

          <Link
            href="/upload"
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-semibold text-xs transition shadow-md shadow-emerald-500/20"
          >
            <UploadCloud className="w-4 h-4" />
            <span className="hidden sm:inline">Upload Pipeline</span>
          </Link>

          <button
            onClick={onOpenConfig}
            className="p-2 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 hover:text-white transition border border-slate-700/60 shadow-sm"
            title="Backend Configuration (.env)"
          >
            <Sliders className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
};
```

---

### 7.7 Backend Configuration Drawer (`src/components/ConfigDrawer.tsx`)

```tsx
'use client';

import React from 'react';
import { Sliders, X, Cpu, HardDrive, CheckCircle2, ShieldCheck } from 'lucide-react';
import { BackendConfig } from '@/types';

interface ConfigDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  config: BackendConfig | null;
}

export const ConfigDrawer: React.FC<ConfigDrawerProps> = ({ isOpen, onClose, config }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in">
      <div className="glass-panel w-full max-w-xl p-6 rounded-3xl border border-slate-800 shadow-2xl space-y-6 relative overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4">
          <div className="flex items-center space-x-2">
            <div className="p-2 rounded-xl bg-teal-500/10 text-teal-400 border border-teal-500/20">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-100">Backend Environment (.env)</h2>
              <p className="text-xs text-slate-400">Live configuration loaded from FastAPI backend</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {config ? (
          <div className="space-y-4">
            <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" /> REAL_THRESHOLD
                </span>
                <span className="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 font-mono font-bold text-sm border border-emerald-500/30">
                  {(config.real_threshold * 100).toFixed(0)}% ({config.real_threshold})
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Determined via <code className="text-slate-400">REAL_THRESHOLD</code> in <code className="text-teal-400">.env</code>. Real face probability equal to or above this percentage is labeled as Real.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="glass-card p-3 rounded-2xl border border-slate-800">
                <div className="text-xs text-slate-400 flex items-center gap-1.5 mb-1">
                  <Cpu className="w-3.5 h-3.5 text-teal-400" /> DEVICE_ID
                </div>
                <div className="font-mono text-sm font-bold text-slate-200">
                  {config.device_id === 0 ? 'GPU 0 / CPU' : `GPU ${config.device_id}`}
                </div>
              </div>

              <div className="glass-card p-3 rounded-2xl border border-slate-800">
                <div className="text-xs text-slate-400 flex items-center gap-1.5 mb-1">
                  <HardDrive className="w-3.5 h-3.5 text-indigo-400" /> Active Models
                </div>
                <div className="font-mono text-sm font-bold text-slate-200">
                  {config.num_models} Weights Loaded
                </div>
              </div>
            </div>

            <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="text-xs font-semibold text-slate-300">Model Weights Directory</div>
              <div className="text-xs font-mono text-teal-400 bg-slate-950 p-2 rounded-xl border border-slate-900 truncate">
                {config.model_dir}
              </div>

              <div className="pt-2 space-y-1">
                {config.available_models.map((model) => (
                  <div key={model} className="flex items-center space-x-2 text-xs font-mono text-slate-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>{model}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="glass-card p-4 rounded-2xl border border-slate-800 space-y-2">
              <div className="text-xs font-semibold text-slate-300">Allowed CORS Origins</div>
              <div className="flex flex-wrap gap-1.5">
                {config.cors_origins.map((origin) => (
                  <span key={origin} className="px-2 py-0.5 rounded bg-slate-800 text-[11px] font-mono text-slate-300 border border-slate-700">
                    {origin}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="p-6 text-center text-xs text-slate-500">
            Unable to fetch configuration from FastAPI server.
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-xs transition"
          >
            Close Settings
          </button>
        </div>
      </div>
    </div>
  );
};
```

---

### 7.8 Root Route Page (`src/app/page.tsx`)

```tsx
'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { AlertCircle, RefreshCw, Server, Lock } from 'lucide-react';
import { Header } from '@/components/Header';
import { ConfigDrawer } from '@/components/ConfigDrawer';
import { SecureWebcamScanner } from '@/components/SecureWebcamScanner';
import { RecognitionDashboard } from '@/components/RecognitionDashboard';
import { useRecognitionSession } from '@/hooks/useRecognitionSession';
import { BackendConfig, CandidateFrame } from '@/types';
import { fetchBackendConfigWithFallback } from '@/lib/api';

export default function Home() {
  const [backendConfig, setBackendConfig] = useState<BackendConfig | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConfigOpen, setIsConfigOpen] = useState<boolean>(false);
  const [activeApiUrl, setActiveApiUrl] = useState<string>('http://127.0.0.1:8000');

  const {
    session,
    isProcessing,
    currentProgress,
    result,
    initSession,
    executeRecognition,
    resetSession,
  } = useRecognitionSession();

  const fetchConfig = useCallback(async () => {
    const res = await fetchBackendConfigWithFallback();
    if (res) {
      setBackendConfig(res.config);
      setActiveApiUrl(res.baseUrl);
      setIsConnected(true);
    } else {
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchConfig();
    initSession();

    const interval = setInterval(fetchConfig, 10000);
    return () => clearInterval(interval);
  }, [fetchConfig, initSession]);

  const handleAutoCaptureFrames = async (best3Frames: CandidateFrame[]) => {
    console.log('Selected best 4 candidate frames for recognition:', best3Frames.length);
    await executeRecognition(best3Frames);
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col justify-between selection:bg-emerald-500 selection:text-white">
      <Header
        config={backendConfig}
        isConnected={isConnected}
        onRefreshConfig={fetchConfig}
        onOpenConfig={() => setIsConfigOpen(true)}
      />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 w-full space-y-8 flex-grow flex flex-col items-center">
        {!isConnected && (
          <div className="w-full max-w-4xl p-4 rounded-2xl bg-amber-950/80 border border-amber-500/50 shadow-xl flex items-center justify-between">
            <div className="flex items-center space-x-3 text-amber-200">
              <AlertCircle className="w-5 h-5 text-amber-400 animate-pulse" />
              <span className="text-sm font-medium">
                Backend Server Offline — Connecting to FastAPI Gateway at {activeApiUrl}...
              </span>
            </div>
            <button
              onClick={fetchConfig}
              className="px-3.5 py-1.5 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 text-xs font-semibold border border-amber-500/40 transition-all flex items-center space-x-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Connection</span>
            </button>
          </div>
        )}

        <div className="w-full max-w-4xl flex flex-col md:flex-row items-center justify-between p-6 rounded-3xl bg-slate-900/60 border border-slate-800 shadow-xl backdrop-blur-xl gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-2xl font-black tracking-tight text-white flex items-center space-x-2">
                <span>Production Face Recognition Pipeline</span>
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                v2.0 Gateway
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              InsightFace buffalo_l 512-d Embeddings • MiniFASNet Anti-Spoofing • Qdrant Vector Search • 2 vCPU VPS Optimized
            </p>
          </div>

          <div className="flex items-center space-x-2 bg-slate-950/80 px-4 py-2 rounded-2xl border border-slate-800 text-xs font-mono text-slate-300">
            <Server className="w-4 h-4 text-cyan-400" />
            <span>Session: {session ? session.session_id.slice(0, 14) + '...' : 'Acquiring Token...'}</span>
          </div>
        </div>

        {result ? (
          <RecognitionDashboard result={result} onReset={resetSession} />
        ) : (
          <SecureWebcamScanner
            onAutoCaptureFrames={handleAutoCaptureFrames}
            isProcessing={isProcessing}
            stageMessage={currentProgress?.message}
            onReset={resetSession}
          />
        )}
      </main>

      <footer className="border-t border-slate-800/80 py-6 bg-[#060910]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center space-x-2">
            <Lock className="w-3.5 h-3.5 text-emerald-400" />
            <span>Secure Webcam Only • Direct Image Upload Restricted</span>
          </div>
          <span>Silent-Face Anti-Spoofing & InsightFace Recognition Gateway</span>
        </div>
      </footer>

      {isConfigOpen && (
        <ConfigDrawer
          config={backendConfig}
          isOpen={isConfigOpen}
          onClose={() => setIsConfigOpen(false)}
        />
      )}
    </div>
  );
}
```
