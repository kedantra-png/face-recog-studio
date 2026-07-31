# Debug Step-by-Step Performance Logger Registry

This document lists all step-by-step performance timing print statements and console loggers added to the backend terminal output and browser console. Use this registry to locate or remove timing instrumentation in the future.

---

## 1. Backend Terminal Step Timers

### `src/pipeline/api/recognition_routes.py`
- **Location**: Inside `POST /api/v2/recognition/verify` (around lines 355–375)
- **Function**: `verify_recognition`
- **Printed Logs**:
  - `[STEP 1/7] FRAME DECODING & INTEGRITY`
  - `[STEP 2/7] BEST FRAME EVALUATION`
  - `[STEP 3/7] LANDMARK ALIGNMENT`
  - `[STEP 4/7] MINI-FASNET ANTI-SPOOF`
  - `[STEP 5/7] INSIGHTFACE EMBEDDING`
  - `[STEP 6/7] QDRANT VECTOR SEARCH`
  - `[STEP 7/7] CONFIDENCE RE-RANKING`
  - `[PIPELINE COMPLETE] Total Latency`

### `src/pipeline/api/routes.py`
- **Location**: Inside `POST /api/v2/upload/search-debug` (around lines 240–255)
- **Function**: `debug_direct_image_search`
- **Printed Logs**:
  - `[STEP 1/3] INSIGHTFACE 512-D EMBEDDING`
  - `[STEP 2/3] QDRANT VECTOR SEARCH`
  - `[STEP 3/3] CONFIDENCE RE-RANKING`
  - `[DIRECT SEARCH COMPLETE] Total Latency`

---

## 2. Frontend Browser Console Loggers

### `frontend/src/components/upload/DirectSearchDebugger.tsx`
- **Location**: Inside `handleSearchCandidate` (around lines 105–125)
- **Console Logs**:
  - `[FRONTEND CAMERA FACE SEARCH]` (Group header)
  - `[FRONTEND STEP 1/4] Snap Video Canvas Frame created`
  - `[FRONTEND STEP 2/4] Transmitting image to POST /api/v2/upload/search-debug`
  - `[FRONTEND STEP 3/4] Received HTTP response in XXms`
  - `[FRONTEND STEP 4/4] Processed Search Results`
  - `[FRONTEND SEARCH COMPLETE] Total Frontend Latency`

---

## How to Remove All Timing Instrumentation

To remove step timing logs in the future:
1. Open [recognition_routes.py](file:///d:/Silent-Face-Anti-Spoofing/Silent-Face-Anti-Spoofing-master/src/pipeline/api/recognition_routes.py) and remove the `print(f"\n==================== [BACKEND RECOGNITION PIPELINE STEP-BY-STEP] =================...")` block.
2. Open [routes.py](file:///d:/Silent-Face-Anti-Spoofing/Silent-Face-Anti-Spoofing-master/src/pipeline/api/routes.py) and remove the `print(f"\n==================== [DIRECT SEARCH DEBUGGER PIPELINE] =================...")` block.
3. Open [DirectSearchDebugger.tsx](file:///d:/Silent-Face-Anti-Spoofing/Silent-Face-Anti-Spoofing-master/frontend/src/components/upload/DirectSearchDebugger.tsx) and remove `console.group` and `console.log` lines inside `handleSearchCandidate`.
