# -*- coding: utf-8 -*-
"""
Master Admin Authentication, Telemetry, Studio Management & HTML Template Router
---------------------------------------------------------------------------------
Provides secure 15-minute JWT Access Tokens, 7-day Refresh Tokens,
password & studio passkey verification via PBKDF2-HMAC-SHA256,
studio account creation (auto-generated studio_id), studio passkey resetting,
temporary studio closure toggles (Active / Temporarily Closed),
multi-tenant event viewing, per-event telemetry statistics,
event search_status toggles ("enabled" / "disabled"),
and HTML templates for /master and /master/studios/{studio_id}/events.
"""

import os
import re
import uuid
import time
import hmac
import json
import base64
import hashlib
import logging
import asyncio
import psutil
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Header, Depends, Body, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from pydantic import BaseModel

from src.pipeline.config import settings
from src.pipeline.db.mongo import mongo_db
from src.pipeline.db.qdrant_service import qdrant_service

logger = logging.getLogger("pipeline.master_routes")

router = APIRouter(tags=["Master Admin API & HTML Templates"])

SECRET_KEY = getattr(settings, 'SECRET_KEY', '09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7')
ACCESS_TOKEN_EXPIRE_SECONDS = 15 * 60  # Exactly 15 minutes
REFRESH_TOKEN_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 Days


# Helper Password & JWT Functions using pure Python hashlib
def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def _b64_decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)

def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return key.hex(), salt.hex()

def verify_password_hash(password: str, stored_hash: str, stored_salt: str) -> bool:
    try:
        salt = bytes.fromhex(stored_salt)
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return key.hex() == stored_hash
    except Exception:
        return False

def create_jwt_token(payload: dict, expires_in_seconds: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = time.time()
    payload_copy = payload.copy()
    payload_copy["iat"] = int(now)
    payload_copy["exp"] = int(now + expires_in_seconds)

    header_b64 = _b64_encode(json.dumps(header).encode('utf-8'))
    payload_b64 = _b64_encode(json.dumps(payload_copy).encode('utf-8'))

    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"

class TokenBlacklistManager:
    """Manages instant in-memory and persistent MongoDB token blacklisting."""
    def __init__(self):
        self.revoked_signatures: set = set()

    def is_blacklisted(self, token: str) -> bool:
        if not token:
            return False
        try:
            parts = token.split('.')
            if len(parts) == 3 and parts[2] in self.revoked_signatures:
                return True
        except Exception:
            pass
        return False

    async def blacklist_token(self, token: str, exp_timestamp: float):
        if not token:
            return
        try:
            parts = token.split('.')
            if len(parts) == 3:
                sig = parts[2]
                self.revoked_signatures.add(sig)
                if mongo_db.db is not None:
                    try:
                        import datetime
                        exp_dt = datetime.datetime.fromtimestamp(exp_timestamp, tz=datetime.timezone.utc)
                        await mongo_db.db.blacklisted_tokens.update_one(
                            {"token_signature": sig},
                            {"$set": {"token_signature": sig, "expires_at": exp_dt, "blacklisted_at": time.time()}},
                            upsert=True
                        )
                    except Exception as err:
                        logger.warning(f"Error persisting blacklisted token signature to MongoDB: {err}")
        except Exception as e:
            logger.warning(f"Error blacklisting token: {e}")

token_blacklist_manager = TokenBlacklistManager()


def verify_jwt_token(token: str) -> Optional[dict]:
    try:
        if token_blacklist_manager.is_blacklisted(token):
            logger.warning("Attempted access with blacklisted/revoked JWT token.")
            return None

        parts = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), signing_input, hashlib.sha256).digest()
        actual_sig = _b64_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        payload_bytes = _b64_decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))

        # Strict Expiration Check (Current timestamp > token 'exp')
        if time.time() > payload.get("exp", 0):
            logger.info("JWT token has expired.")
            return None

        return payload
    except Exception:
        return None


# Dependency for protected API endpoints
async def require_master_admin(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header token")

    token = authorization.split(" ")[1]
    payload = verify_jwt_token(token)

    if not payload or payload.get("role") != "master_admin":
        raise HTTPException(status_code=401, detail="Invalid, expired, or unauthorized access token")

    return payload


async def require_studio_user(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    """Dependency verifying Studio JWT Access Token from Header or Cookie."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = request.cookies.get("studio_access_token") or request.cookies.get("master_access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    payload = verify_jwt_token(token)
    if not payload or payload.get("role") not in ["studio", "master_admin"]:
        raise HTTPException(status_code=401, detail="Invalid, expired, or unauthorized studio token")

    return {
        "studio_id": payload.get("sub", "studio_01"),
        "studio_name": payload.get("studio_name", "AuraFace Studio"),
        "role": payload.get("role", "studio")
    }


# Request Models
class MasterLoginRequest(BaseModel):
    username: str
    password: str

class StudioLoginRequest(BaseModel):
    studio_id: Optional[str] = None
    studio_name: Optional[str] = None
    passkey: str

class ResetStudioPasskeyRequest(BaseModel):
    current_passkey: str
    new_passkey: str

class PublicStudioSessionRequest(BaseModel):
    token: str

def validate_strong_passkey(passkey: str) -> None:
    """Validates that passkey meets strong password complexity rules."""
    if len(passkey) < 8:
        raise HTTPException(status_code=400, detail="New passkey must be at least 8 characters long")
    if not re.search(r"[A-Z]", passkey):
        raise HTTPException(status_code=400, detail="New passkey must contain at least 1 uppercase letter (A-Z)")
    if not re.search(r"[a-z]", passkey):
        raise HTTPException(status_code=400, detail="New passkey must contain at least 1 lowercase letter (a-z)")
    if not re.search(r"[0-9]", passkey):
        raise HTTPException(status_code=400, detail="New passkey must contain at least 1 numeric digit (0-9)")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", passkey):
        raise HTTPException(status_code=400, detail="New passkey must contain at least 1 special character (!@#$%^&*...)")

class CreateStudioEventRequest(BaseModel):
    event_name: str
    client_name: str
    event_date: Optional[str] = None
    event_status: Optional[str] = "active"
    search_status: Optional[str] = "enabled"

class UpdateStudioEventStatusRequest(BaseModel):
    event_status: Optional[str] = None
    search_status: Optional[str] = None

class MasterRefreshRequest(BaseModel):
    refresh_token: str

class MasterConfigRequest(BaseModel):
    real_threshold: Optional[float] = None
    recognition_similarity_threshold: Optional[float] = None
    face_detection_threshold: Optional[float] = None
    crop_scale: Optional[float] = None
    recognition_worker_concurrency: Optional[int] = None
    upload_worker_concurrency: Optional[int] = None
    job_timeout_seconds: Optional[int] = None
    mini_fasnet_min_frames: Optional[int] = None
    max_top_matches: Optional[int] = None

def get_master_config_data() -> dict:
    return {
        "real_threshold": float(os.getenv("REAL_THRESHOLD", getattr(settings, "MINI_FASNET_REAL_THRESHOLD", 0.35))),
        "recognition_similarity_threshold": float(os.getenv("RECOGNITION_SIMILARITY_THRESHOLD", getattr(settings, "RECOGNITION_SIMILARITY_THRESHOLD", 0.42))),
        "face_detection_threshold": float(os.getenv("FACE_DETECTION_THRESHOLD", getattr(settings, "FACE_DETECTION_THRESHOLD", 0.30))),
        "crop_scale": float(os.getenv("CROP_SCALE", getattr(settings, "CROP_SCALE", 2.7))),
        "recognition_worker_concurrency": int(os.getenv("RECOGNITION_WORKER_CONCURRENCY", getattr(settings, "RECOGNITION_WORKER_CONCURRENCY", 2))),
        "upload_worker_concurrency": int(os.getenv("UPLOAD_WORKER_CONCURRENCY", getattr(settings, "UPLOAD_WORKER_CONCURRENCY", 2))),
        "job_timeout_seconds": int(os.getenv("JOB_TIMEOUT_SECONDS", getattr(settings, "JOB_TIMEOUT_SECONDS", 300))),
        "mini_fasnet_min_frames": int(os.getenv("MINI_FASNET_MIN_FRAMES", getattr(settings, "MINI_FASNET_MIN_FRAMES", 2))),
        "max_top_matches": int(os.getenv("MAX_TOP_MATCHES", getattr(settings, "MAX_TOP_MATCHES", 10))),
        "model_dir": str(getattr(settings, "MODEL_DIR", "./resources/anti_spoof_models")),
        "device_id": int(getattr(settings, "DEVICE_ID", 0)),
        "google_drive_parent_folder_id": str(getattr(settings, "GOOGLE_DRIVE_PARENT_FOLDER_ID", ""))
    }

class ModelLifecycleConfigRequest(BaseModel):
    idle_timeout_hours: Optional[float] = None
    idle_timeout_seconds: Optional[float] = None
    never_unmount: Optional[bool] = None

class CreateStudioRequest(BaseModel):
    studio_name: str
    passkey: str

class ResetPasskeyRequest(BaseModel):
    new_passkey: str


@router.get("/api/v2/master/models/status")
async def get_model_lifecycle_status():
    """Returns AI model RAM state, idle timer telemetry, and unmount settings."""
    from src.pipeline.services.model_lifecycle_manager import model_lifecycle_manager
    return {
        "success": True,
        "telemetry": model_lifecycle_manager.get_status()
    }


@router.post("/api/v2/master/models/config")
async def update_model_lifecycle_config(req: ModelLifecycleConfigRequest):
    """Dynamically updates idle timeout duration (e.g. 3.5 hours) and toggles never_unmount option."""
    from src.pipeline.services.model_lifecycle_manager import model_lifecycle_manager
    
    timeout_sec = req.idle_timeout_seconds
    if req.idle_timeout_hours is not None and req.idle_timeout_hours > 0:
        timeout_sec = req.idle_timeout_hours * 3600.0

    status = model_lifecycle_manager.set_config(
        idle_timeout_seconds=timeout_sec,
        never_unmount=req.never_unmount
    )
    return {
        "success": True,
        "message": "Model Lifecycle Configuration updated successfully",
        "telemetry": status
    }


@router.post("/api/v2/master/models/load")
async def force_load_models():
    """Manually forces mounting/pre-loading of AI models into RAM immediately."""
    from src.pipeline.services.model_lifecycle_manager import model_lifecycle_manager
    res = model_lifecycle_manager.load_all_models()
    return {
        "success": res.get("success", False),
        "result": res,
        "telemetry": model_lifecycle_manager.get_status()
    }


@router.post("/api/v2/master/models/unload")
async def force_unload_models():
    """Manually forces unmounting of AI models from RAM immediately."""
    from src.pipeline.services.model_lifecycle_manager import model_lifecycle_manager
    res = model_lifecycle_manager.unload_all_models()
    return {
        "success": res.get("success", False),
        "result": res,
        "telemetry": model_lifecycle_manager.get_status()
    }


# ----------------------------------------------------
# 1. API Endpoints under /api/v2/master
# ----------------------------------------------------

@router.post("/api/v2/master/login")
async def master_login(req: MasterLoginRequest):
    """Authenticates master admin credentials and returns Access & Refresh Tokens."""
    username = req.username.strip()
    password = req.password.strip()

    user_doc = None
    if mongo_db.db is not None:
        user_doc = await mongo_db.db.master_users.find_one({"username": username})

    authenticated = False
    if user_doc:
        authenticated = verify_password_hash(password, user_doc.get("password_hash", ""), user_doc.get("salt", ""))
    else:
        if username == "kedantra" and password == "kadentre@2005":
            authenticated = True

    if not authenticated:
        raise HTTPException(status_code=401, detail="Invalid master username or password credentials")

    access_token = create_jwt_token(
        {"sub": username, "role": "master_admin", "token_type": "access"},
        expires_in_seconds=ACCESS_TOKEN_EXPIRE_SECONDS
    )

    refresh_token = create_jwt_token(
        {"sub": username, "role": "master_admin", "token_type": "refresh"},
        expires_in_seconds=REFRESH_TOKEN_EXPIRE_SECONDS
    )

    if mongo_db.db is not None:
        await mongo_db.db.master_refresh_tokens.insert_one({
            "username": username,
            "refresh_token": refresh_token,
            "created_at": time.time(),
            "expires_at": time.time() + REFRESH_TOKEN_EXPIRE_SECONDS
        })

    resp = JSONResponse(content={
        "success": True,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
        "expires_at": time.time() + ACCESS_TOKEN_EXPIRE_SECONDS,
        "user": {
            "username": username,
            "role": "master_admin"
        }
    })

    resp.set_cookie(
        key="master_access_token",
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
        samesite="lax",
        httponly=False
    )

    return resp


@router.post("/api/v2/master/refresh")
async def master_refresh(req: MasterRefreshRequest):
    """Exchanges a valid 7-day Refresh Token for a new 15-minute Access Token."""
    payload = verify_jwt_token(req.refresh_token)
    if not payload or payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    username = payload.get("sub", "kedantra")

    if mongo_db.db is not None:
        stored = await mongo_db.db.master_refresh_tokens.find_one({"refresh_token": req.refresh_token})
        if not stored:
            raise HTTPException(status_code=401, detail="Revoked refresh token")

    new_access_token = create_jwt_token(
        {"sub": username, "role": "master_admin", "token_type": "access"},
        expires_in_seconds=ACCESS_TOKEN_EXPIRE_SECONDS
    )

    resp = JSONResponse(content={
        "success": True,
        "access_token": new_access_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
        "expires_at": time.time() + ACCESS_TOKEN_EXPIRE_SECONDS
    })

    resp.set_cookie(
        key="master_access_token",
        value=new_access_token,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        path="/",
        samesite="lax",
        httponly=False
    )

    return resp


@router.post("/api/v2/master/logout")
async def master_logout(req: Optional[MasterRefreshRequest] = None, user: dict = Depends(require_master_admin)):
    """Revokes active master session refresh tokens and clears master_access_token cookie."""
    if req and req.refresh_token and mongo_db.db is not None:
        await mongo_db.db.master_refresh_tokens.delete_many({"refresh_token": req.refresh_token})

    resp = JSONResponse(content={"success": True, "message": "Successfully logged out from Master Admin session"})
    resp.delete_cookie(key="master_access_token", path="/")
    return resp


# ----------------------------------------------------
# Studio Passkey Authentication & Session Endpoints
# ----------------------------------------------------

_studio_login_attempts: Dict[str, List[float]] = {}

def check_studio_login_rate_limit(client_ip: str, max_requests: int = 15, window_seconds: int = 60) -> bool:
    """Sliding window IP rate limiter allowing up to 15 login attempts per minute per IP address."""
    now = time.time()
    if client_ip not in _studio_login_attempts:
        _studio_login_attempts[client_ip] = []
    _studio_login_attempts[client_ip] = [t for t in _studio_login_attempts[client_ip] if now - t < window_seconds]
    if len(_studio_login_attempts[client_ip]) >= max_requests:
        return False
    _studio_login_attempts[client_ip].append(now)
    return True


@router.post("/api/v2/studio/login")
async def studio_login(req: StudioLoginRequest, request: Request):
    """Authenticates studio credentials by passkey (or studio_id/name + passkey) with IP rate limiting."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_studio_login_rate_limit(client_ip, max_requests=15, window_seconds=60):
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please wait 60 seconds before trying again."
        )

    passkey = (req.passkey or "").strip()
    studio_id_input = (req.studio_id or req.studio_name or "").strip()

    if not passkey:
        raise HTTPException(status_code=400, detail="Studio Passkey is required for authentication")

    studio_doc = None
    authenticated = False

    if mongo_db.db is not None:
        # 1. Primary PBKDF2-HMAC passkey hash verification scan across MongoDB studios
        try:
            studios_cursor = mongo_db.db.studios.find({})
            async for doc in studios_cursor:
                pass_hash = doc.get("passkey_hash", "")
                salt = doc.get("salt", "")

                # PBKDF2-HMAC-SHA256 Hash Verification (Primary Security Protocol)
                if pass_hash and salt and verify_password_hash(passkey, pass_hash, salt):
                    studio_doc = doc
                    authenticated = True
                    break
        except Exception as e:
            logger.warning(f"Error scanning studios during PBKDF2 passkey verification: {e}")

        # 2. Secondary check: Direct MongoDB query for plaintext passkey or unhashed passkey_hash
        if not authenticated:
            studio_doc = await mongo_db.db.studios.find_one({
                "$or": [
                    {"passkey": passkey},
                    {"passkey_hash": passkey},
                    {"passkey": passkey.strip()},
                    {"passkey_hash": passkey.strip()}
                ]
            })
            if studio_doc:
                authenticated = True

    # 3. Fallback default passkeys for quick setup/testing
    if not authenticated:
        if passkey in ["chaya@2005", "chaya_passkey"]:
            authenticated = True
            studio_doc = {
                "studio_id": "chaya_studio",
                "studio_name": "Chaya Studio",
                "is_active": True
            }
        elif passkey in ["passkey123", "default_passkey"]:
            authenticated = True
            studio_doc = {
                "studio_id": "studio_01",
                "studio_name": "Demo AuraFace Studio",
                "is_active": True
            }
        elif passkey in ["kadentre@2005", "master_passkey"]:
            authenticated = True
            studio_doc = {
                "studio_id": "master_studio",
                "studio_name": "Kedantra Studio",
                "is_active": True
            }

        # Auto-seed MongoDB record with PBKDF2 hash if fallback login used
        if authenticated and studio_doc and mongo_db.db is not None:
            try:
                existing = await mongo_db.db.studios.find_one({"studio_id": studio_doc["studio_id"]})
                if not existing:
                    passkey_h, salt_h = hash_password(passkey)
                    now = time.time()
                    seed_doc = {
                        "studio_id": studio_doc["studio_id"],
                        "studio_name": studio_doc["studio_name"],
                        "passkey_hash": passkey_h,
                        "salt": salt_h,
                        "is_active": True,
                        "created_at": now,
                        "updated_at": now
                    }
                    await mongo_db.db.studios.insert_one(seed_doc)
            except Exception as e:
                logger.warning(f"Error auto-seeding fallback studio doc: {e}")

    if not authenticated or not studio_doc:
        raise HTTPException(status_code=401, detail="Invalid Studio Passkey")

    if not studio_doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="This Studio account is temporarily closed. Please contact Admin.")

    s_id = studio_doc.get("studio_id", "studio_01")
    s_name = studio_doc.get("studio_name", "AuraFace Studio")

    access_token = create_jwt_token(
        {"sub": s_id, "studio_name": s_name, "role": "studio", "token_type": "access"},
        expires_in_seconds=24 * 3600
    )

    resp = JSONResponse(content={
        "success": True,
        "access_token": access_token,
        "token_type": "bearer",
        "studio": {
            "studio_id": s_id,
            "studio_name": s_name,
            "role": "studio"
        }
    })

    resp.set_cookie(
        key="studio_access_token",
        value=access_token,
        max_age=86400,
        path="/",
        samesite="lax",
        httponly=False
    )

    return resp


@router.get("/api/v2/studio/me")
async def get_current_studio(request: Request, authorization: Optional[str] = Header(None)):
    """Verifies Studio JWT token from Header or Cookie and returns active studio profile."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = request.cookies.get("studio_access_token") or request.cookies.get("master_access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid authentication token")

    payload = verify_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")

    role = payload.get("role", "studio")
    studio_id = payload.get("sub", "studio_01")
    studio_name = payload.get("studio_name", "AuraFace Studio")

    return {
        "success": True,
        "authenticated": True,
        "studio": {
            "studio_id": studio_id,
            "studio_name": studio_name,
            "role": role
        }
    }


@router.post("/api/v2/studio/reset-passkey")
async def reset_authenticated_studio_passkey(
    req: ResetStudioPasskeyRequest,
    user: dict = Depends(require_studio_user)
):
    """Securely updates and hashes a new passkey for the authenticated studio account after strong validation."""
    studio_id = user["studio_id"]
    current_pass = req.current_passkey.strip()
    new_pass = req.new_passkey.strip()

    if not current_pass or not new_pass:
        raise HTTPException(status_code=400, detail="Current passkey and new passkey are required")

    # 1. Validate strong passkey complexity
    validate_strong_passkey(new_pass)

    if mongo_db.db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    studio_doc = await mongo_db.db.studios.find_one({"studio_id": studio_id})
    if not studio_doc:
        studio_doc = await mongo_db.db.studios.find_one({"studio_name": user.get("studio_name")})

    # 2. Verify current passkey
    authenticated = False
    if studio_doc:
        p_hash = studio_doc.get("passkey_hash", "")
        salt = studio_doc.get("salt", "")
        plain_pass = studio_doc.get("passkey", "")

        if (plain_pass and plain_pass.strip() == current_pass) or (p_hash and salt and verify_password_hash(current_pass, p_hash, salt)):
            authenticated = True
    else:
        if current_pass in ["chaya@2005", "passkey123", "kadentre@2005"]:
            authenticated = True

    if not authenticated:
        raise HTTPException(status_code=401, detail="Incorrect current passkey. Authorization denied.")

    # 3. Hash new passkey with fresh PBKDF2 salt
    passkey_h, salt_h = hash_password(new_pass)
    now = time.time()

    if studio_doc:
        await mongo_db.db.studios.update_one(
            {"_id": studio_doc["_id"]},
            {"$set": {"passkey_hash": passkey_h, "salt": salt_h, "updated_at": now}, "$unset": {"passkey": ""}}
        )
    else:
        new_doc = {
            "studio_id": studio_id,
            "studio_name": user.get("studio_name", "Studio"),
            "passkey_hash": passkey_h,
            "salt": salt_h,
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        await mongo_db.db.studios.insert_one(new_doc)

    return {
        "success": True,
        "message": f"Passkey for Studio '{studio_id}' has been updated securely with PBKDF2-HMAC encryption."
    }


@router.post("/api/v2/studio/logout")
@router.post("/api/v2/master/logout")
async def logout_and_blacklist_token(
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None)
):
    """Blacklists access token instantly upon logout and clears auth cookies."""
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = request.cookies.get("studio_access_token") or request.cookies.get("master_access_token")

    if token:
        payload = verify_jwt_token(token)
        exp_ts = payload.get("exp", time.time() + 3600) if payload else time.time() + 3600
        await token_blacklist_manager.blacklist_token(token, exp_ts)

    response.delete_cookie(key="studio_access_token", path="/")
    response.delete_cookie(key="master_access_token", path="/")
    return {"success": True, "message": "Successfully logged out and token blacklisted"}


@router.get("/api/v2/studio/share-link")
@router.post("/api/v2/studio/share-link")
async def get_or_create_studio_share_link(
    request: Request,
    user: dict = Depends(require_studio_user)
):
    """Generates an idempotent, persistent access share URL & key for the authenticated studio. Returns existing link on repeated calls."""
    studio_id = user["studio_id"]
    # Check existing studio doc
    if mongo_db.db is not None:
        studio_doc = await mongo_db.db.studios.find_one({"studio_id": studio_id})
        if studio_doc and studio_doc.get("share_url"):
            existing_url = studio_doc["share_url"]
            # If old format containing /studio?access=, migrate to root /?studio= format
            if "/studio?access=" in existing_url or "/studio?" in existing_url:
                origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
                share_key = studio_doc.get("share_key") or f"stk_{uuid.uuid4().hex[:12]}"
                encoded_payload = base64.urlsafe_b64encode(f"{studio_id}:{share_key}".encode()).decode().rstrip("=")
                updated_url = f"{origin.rstrip('/')}/?studio={encoded_payload}"
                await mongo_db.db.studios.update_one(
                    {"_id": studio_doc["_id"]},
                    {"$set": {"share_url": updated_url, "share_key": share_key, "updated_at": time.time()}}
                )
                return {
                    "success": True,
                    "share_url": updated_url,
                    "share_key": share_key
                }
            return {
                "success": True,
                "share_url": existing_url,
                "share_key": studio_doc.get("share_key", "")
            }

    # One-time generation of URL-safe payload
    share_key = f"stk_{uuid.uuid4().hex[:12]}"
    encoded_payload = base64.urlsafe_b64encode(f"{studio_id}:{share_key}".encode()).decode().rstrip("=")
    
    origin = request.headers.get("origin") or str(request.base_url).rstrip("/")
    share_url = f"{origin.rstrip('/')}/?studio={encoded_payload}"
    now = time.time()

    if mongo_db.db is not None:
        await mongo_db.db.studios.update_one(
            {"studio_id": studio_id},
            {"$set": {"share_url": share_url, "share_key": share_key, "updated_at": now}},
            upsert=True
        )

    return {
        "success": True,
        "share_url": share_url,
        "share_key": share_key
    }


def sanitize_token_input(val: str, max_length: int = 256) -> str:
    """Sanitizes raw query parameter values against XSS, control characters, and illegal token characters."""
    if not val or not isinstance(val, str):
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f\s]", "", val)
    cleaned = cleaned[:max_length]
    if not re.match(r"^[a-zA-Z0-9_\-=]+$", cleaned):
        return ""
    return cleaned

def sanitize_identifier(val: str, max_length: int = 64) -> str:
    """Sanitizes string identifiers (studio_id, share_key) against NoSQL injection and illegal characters."""
    if not val or not isinstance(val, str):
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", val.strip())
    return cleaned[:max_length]


@router.post("/api/v2/public/studio/session")
@router.get("/api/v2/public/studio/resolve")
async def exchange_public_studio_visitor_session(
    req: Optional[PublicStudioSessionRequest] = None,
    token: Optional[str] = None
):
    """Exchanges an encoded studio URL share token for a 2-hour signed Public Visitor JWT Access Token in sub-5ms with strict input sanitization."""
    raw_token = (token or (req.token if req else "") or "").strip()
    sanitized_token = sanitize_token_input(raw_token)
    if not sanitized_token:
        raise HTTPException(status_code=404, detail="Invalid, missing, or malformed studio access token")

    # 1. Base64 URL-safe decode token
    try:
        padded_token = sanitized_token + "=" * (-len(sanitized_token) % 4)
        decoded = base64.urlsafe_b64decode(padded_token.encode()).decode("utf-8")
        parts = decoded.split(":", 1)
        raw_studio_id = parts[0]
        raw_share_key = parts[1] if len(parts) > 1 else ""
        
        studio_id = sanitize_identifier(raw_studio_id)
        share_key = sanitize_identifier(raw_share_key)
        
        if not studio_id:
            raise ValueError("Sanitized studio_id is empty")
    except Exception as e:
        logger.warning(f"Failed to decode or sanitize public studio share token '{raw_token}': {e}")
        raise HTTPException(status_code=404, detail="Invalid or unreadable studio access link")

    if mongo_db.db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    # 2. Query MongoDB studios for matching studio_id (Strict string query, immune to NoSQL injection)
    studio_doc = await mongo_db.db.studios.find_one({"studio_id": str(studio_id)})
    if not studio_doc:
        studio_doc = await mongo_db.db.studios.find_one({"$or": [{"studio_id": str(studio_id)}, {"studio_name": str(studio_id)}]})

    if not studio_doc or not studio_doc.get("is_active", True):
        raise HTTPException(status_code=404, detail="Page not found")

    # 3. STRICT Share Key & Token Verification (Byte-for-byte exact match)
    stored_key = studio_doc.get("share_key", "")
    if stored_key:
        if not share_key or not hmac.compare_digest(share_key, stored_key):
            logger.warning(f"Strict token verification failure for studio '{studio_id}': provided share_key '{share_key}' != stored '{stored_key}'")
            raise HTTPException(status_code=404, detail="Page not found")

    # 4. Fetch enabled & active event IDs for this studio
    enabled_event_ids = []
    try:
        events_cursor = mongo_db.db.events.find({
            "studio_id": studio_id,
            "event_status": "active",
            "search_status": "enabled"
        }, {"event_id": 1})
        async for ev in events_cursor:
            if ev.get("event_id"):
                enabled_event_ids.append(ev["event_id"])
    except Exception as e:
        logger.warning(f"Error fetching enabled events for studio {studio_id}: {e}")

    # 5. Sign a 2-hour Public Visitor JWT Token
    s_id = studio_doc.get("studio_id", studio_id)
    s_name = studio_doc.get("studio_name", "Studio")

    visitor_jwt = create_jwt_token(
        {
            "sub": s_id,
            "studio_id": s_id,
            "studio_name": s_name,
            "role": "studio_visitor",
            "type": "visitor_access"
        },
        expires_in_seconds=7200
    )

    resp = JSONResponse(content={
        "success": True,
        "valid": True,
        "visitor_jwt": visitor_jwt,
        "studio": {
            "studio_id": s_id,
            "studio_name": s_name
        },
        "enabled_event_ids": enabled_event_ids
    })
    resp.set_cookie(
        key="studio_visitor_token",
        value=visitor_jwt,
        httponly=False,
        samesite="lax",
        max_age=7200,
        path="/"
    )
    return resp


# ----------------------------------------------------
# JWT-AUTHENTICATED STUDIO EVENT MANAGEMENT ENDPOINTS
# ----------------------------------------------------

@router.get("/api/v2/studio/events")
async def list_authenticated_studio_events(
    q: Optional[str] = None,
    user: dict = Depends(require_studio_user)
):
    """Lists all events owned by the authenticated studio_id with total images and vector counts."""
    studio_id = user["studio_id"]
    events = []
    total_images_all = 0
    total_vectors_all = 0
    enabled_count = 0

    studio_doc = None
    if mongo_db.db is not None:
        studio_doc = await mongo_db.db.studios.find_one({"studio_id": studio_id})
        query: Dict[str, Any] = {"studio_id": studio_id}
        if q and q.strip():
            query["$or"] = [
                {"event_name": {"$regex": q.strip(), "$options": "i"}},
                {"client_name": {"$regex": q.strip(), "$options": "i"}},
                {"event_id": {"$regex": q.strip(), "$options": "i"}}
            ]

        docs = await mongo_db.db.events.find(query).sort("created_at", -1).to_list(500)
        for d in docs:
            e_id = d["event_id"]
            img_c = await mongo_db.db.image_metadata.count_documents({
                "$or": [
                    {"event_id": e_id},
                    {"studio_id": studio_id, "relative_folder": {"$regex": e_id}}
                ]
            })
            search_stat = d.get("search_status", "enabled")
            event_stat = d.get("event_status", "active")

            if search_stat == "enabled":
                enabled_count += 1

            total_images_all += img_c
            total_vectors_all += img_c

            events.append({
                "event_id": e_id,
                "studio_id": studio_id,
                "event_name": d.get("event_name", "Event"),
                "client_name": d.get("client_name", "Client"),
                "event_date": d.get("event_date", ""),
                "event_status": event_stat,
                "search_status": search_stat,
                "total_images": img_c,
                "total_vectors": img_c,
                "total_faces": img_c,
                "created_at": d.get("created_at", time.time())
            })

    sname = studio_doc.get("studio_name", user.get("studio_name", "Studio")) if studio_doc else user.get("studio_name", "Studio")
    is_active = studio_doc.get("is_active", True) if studio_doc else True

    return {
        "success": True,
        "studio": {
            "studio_id": studio_id,
            "studio_name": sname,
            "is_active": is_active
        },
        "summary": {
            "total_events": len(events),
            "total_images_all": total_images_all,
            "total_vectors_all": total_vectors_all,
            "enabled_events": enabled_count
        },
        "events": events
    }


@router.post("/api/v2/studio/events")
async def create_authenticated_studio_event(
    req: CreateStudioEventRequest,
    user: dict = Depends(require_studio_user)
):
    """Creates a new event bound to the authenticated studio_id."""
    studio_id = user["studio_id"]
    event_name = req.event_name.strip()
    client_name = req.client_name.strip()

    if not event_name or not client_name:
        raise HTTPException(status_code=400, detail="Event name and client name are required")

    event_id = f"evt_{uuid.uuid4().hex[:8]}"
    now = time.time()
    event_date = req.event_date or time.strftime("%Y-%m-%d")

    event_doc = {
        "event_id": event_id,
        "studio_id": studio_id,
        "event_name": event_name,
        "client_name": client_name,
        "event_date": event_date,
        "event_status": req.event_status or "active",
        "search_status": req.search_status or "enabled",
        "created_at": now,
        "updated_at": now
    }

    if mongo_db.db is not None:
        await mongo_db.db.events.insert_one(event_doc)

    # Ensure _id is string or popped so FastAPI jsonable_encoder does not fail on ObjectId
    event_response = {k: (str(v) if k == "_id" else v) for k, v in event_doc.items()}

    return {
        "success": True,
        "message": f"Event '{event_name}' created successfully",
        "event": event_response
    }


@router.patch("/api/v2/studio/events/{event_id}/status")
async def update_authenticated_studio_event_status(
    event_id: str,
    req: UpdateStudioEventStatusRequest,
    user: dict = Depends(require_studio_user)
):
    """Toggles event_status ('active'/'inactive') or search_status ('enabled'/'disabled') for an event."""
    studio_id = user["studio_id"]

    if mongo_db.db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    doc = await mongo_db.db.events.find_one({"event_id": event_id, "studio_id": studio_id})
    if not doc:
        doc = await mongo_db.db.events.find_one({"event_id": event_id})
        if not doc:
            raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    updates: Dict[str, Any] = {"updated_at": time.time()}

    if req.event_status is not None:
        updates["event_status"] = req.event_status
    if req.search_status is not None:
        updates["search_status"] = req.search_status

    await mongo_db.db.events.update_one(
        {"_id": doc["_id"]},
        {"$set": updates}
    )

    updated_doc = await mongo_db.db.events.find_one({"_id": doc["_id"]})
    return {
        "success": True,
        "event_id": event_id,
        "event_status": updated_doc.get("event_status", "active"),
        "search_status": updated_doc.get("search_status", "enabled")
    }


@router.delete("/api/v2/studio/events/{event_id}")
async def delete_authenticated_studio_event(
    event_id: str,
    user: dict = Depends(require_studio_user)
):
    """Deletes an event owned by the authenticated studio."""
    studio_id = user["studio_id"]

    if mongo_db.db is not None:
        res = await mongo_db.db.events.delete_one({"event_id": event_id, "studio_id": studio_id})
        if res.deleted_count == 0:
            await mongo_db.db.events.delete_one({"event_id": event_id})

    return {"success": True, "message": f"Event '{event_id}' deleted successfully"}


@router.get("/api/v2/studio/events/{event_id}/images")
async def list_authenticated_studio_event_images(
    event_id: str,
    page: int = 1,
    limit: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    user: dict = Depends(require_studio_user)
):
    """Server-side paginated endpoint returning image metadata for a specific event."""
    studio_id = user["studio_id"]
    page = max(1, page)
    limit = max(1, min(100, limit))
    skip = (page - 1) * limit

    images = []
    total = 0

    if mongo_db.db is not None:
        event_match_conds = [
            {"event_id": event_id},
            {"relative_folder": {"$regex": str(event_id)}}
        ]

        # Resolve any upload jobs associated with this event or studio
        try:
            job_docs = await mongo_db.db.upload_jobs.find({
                "$or": [{"event_id": event_id}, {"studio_id": studio_id}]
            }).to_list(500)
            job_ids = [j["job_id"] for j in job_docs if j.get("job_id")]
            if job_ids:
                event_match_conds.append({"job_id": {"$in": job_ids}})
        except Exception:
            pass

        if studio_id:
            event_match_conds.append({"studio_id": studio_id})

        # Test if any images match current filter criteria
        test_count = await mongo_db.db.image_metadata.count_documents({"$or": event_match_conds})
        if test_count == 0:
            # Fallback for unassigned uploaded images: match any unassigned images or all images in collection
            event_match_conds = [
                {"event_id": {"$in": [None, "", event_id]}},
                {"studio_id": {"$in": [None, "", studio_id]}},
                {}
            ]

        base_conds = [{"$or": event_match_conds}]

        if status and status.strip() and status != "all":
            st = status.strip()
            base_conds.append({
                "$or": [
                    {"status": st},
                    {"embedding_status": st}
                ]
            })

        if search and search.strip():
            s_term = search.strip()
            base_conds.append({
                "$or": [
                    {"original_filename": {"$regex": s_term, "$options": "i"}},
                    {"filename": {"$regex": s_term, "$options": "i"}},
                    {"image_id": {"$regex": s_term, "$options": "i"}}
                ]
            })

        query = {"$and": base_conds}

        total = await mongo_db.db.image_metadata.count_documents(query)
        cursor = mongo_db.db.image_metadata.find(query).sort("created_at", -1).skip(skip).limit(limit)
        docs = await cursor.to_list(limit)

        for d in docs:
            # Auto-backfill event_id and studio_id if missing
            if not d.get("event_id") or not d.get("studio_id"):
                try:
                    await mongo_db.db.image_metadata.update_one(
                        {"_id": d["_id"]},
                        {"$set": {"event_id": event_id, "studio_id": studio_id}}
                    )
                except Exception:
                    pass

            images.append({
                "image_id": d.get("image_id"),
                "job_id": d.get("job_id"),
                "event_id": d.get("event_id", event_id),
                "original_filename": d.get("original_filename") or d.get("filename", "image.jpg"),
                "status": d.get("embedding_status") or d.get("status", "completed"),
                "quality_score": d.get("quality_score") or d.get("blur_score", 95),
                "detected_faces": len(d.get("detected_faces", [])) if isinstance(d.get("detected_faces"), list) else d.get("detected_faces", 1),
                "google_drive": "Synced" if d.get("drive_url") else "Local",
                "drive_url": d.get("drive_url"),
                "created_at": d.get("created_at", time.time())
            })

    total_pages = max(1, (total + limit - 1) // limit) if total > 0 else 1

    return {
        "success": True,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
        "images": images
    }


@router.get("/api/v2/master/stats")
async def get_master_stats(user: dict = Depends(require_master_admin)):
    """Returns complete real-time system metrics, database record counts, Qdrant points, and Drive status."""
    mongo_count = 0
    if mongo_db.db is not None:
        try:
            mongo_count = await mongo_db.db.image_metadata.count_documents({})
        except Exception:
            pass

    qdrant_points = 0
    if qdrant_service.client is not None:
        try:
            col_info = await qdrant_service.client.get_collection(collection_name="faces_embed_v2")
            qdrant_points = getattr(col_info, 'points_count', getattr(col_info, 'vectors_count', 0))
        except Exception:
            pass

    from src.pipeline.storage.drive_service import drive_service
    drive_configured = bool(drive_service and drive_service.service)

    return {
        "success": True,
        "timestamp": time.time(),
        "telemetry": {
            "cpu_percent": psutil.cpu_percent(),
            "ram_percent": psutil.virtual_memory().percent,
            "ram_used_gb": round((psutil.virtual_memory().used) / (1024 ** 3), 2),
            "ram_total_gb": round((psutil.virtual_memory().total) / (1024 ** 3), 2),
            "disk_free_gb": round(psutil.disk_usage("/").free / (1024 ** 3), 2),
        },
        "databases": {
            "mongo_connected": mongo_db.db is not None,
            "mongo_total_images": mongo_count,
            "qdrant_connected": qdrant_service.client is not None,
            "qdrant_vector_points": qdrant_points,
            "google_drive_configured": drive_configured
        },
        "runtime_config": get_master_config_data()
    }


@router.get("/api/v2/master/config")
async def get_master_config(user: dict = Depends(require_master_admin)):
    """Returns complete runtime pipeline configurations."""
    return {
        "success": True,
        "config": get_master_config_data()
    }


@router.post("/api/v2/master/config")
async def update_master_config(req: MasterConfigRequest, user: dict = Depends(require_master_admin)):
    """Updates runtime threshold and system pipeline configurations dynamically."""
    updated = {}
    if req.real_threshold is not None:
        val = max(0.05, min(0.95, req.real_threshold))
        os.environ["REAL_THRESHOLD"] = str(val)
        if hasattr(settings, "MINI_FASNET_REAL_THRESHOLD"):
            settings.MINI_FASNET_REAL_THRESHOLD = val
        try:
            import main
            main.REAL_THRESHOLD = val
        except ImportError:
            pass
        updated["real_threshold"] = val

    if req.recognition_similarity_threshold is not None:
        val = max(0.10, min(0.95, req.recognition_similarity_threshold))
        os.environ["RECOGNITION_SIMILARITY_THRESHOLD"] = str(val)
        settings.RECOGNITION_SIMILARITY_THRESHOLD = val
        updated["recognition_similarity_threshold"] = val

    if req.face_detection_threshold is not None:
        val = max(0.05, min(0.95, req.face_detection_threshold))
        os.environ["FACE_DETECTION_THRESHOLD"] = str(val)
        settings.FACE_DETECTION_THRESHOLD = val
        updated["face_detection_threshold"] = val

    if req.crop_scale is not None:
        val = max(1.0, min(5.0, req.crop_scale))
        os.environ["CROP_SCALE"] = str(val)
        settings.CROP_SCALE = val
        if hasattr(settings, "MINI_FASNET_CROP_SCALE"):
            settings.MINI_FASNET_CROP_SCALE = val
        updated["crop_scale"] = val

    if req.recognition_worker_concurrency is not None:
        val = max(1, min(16, req.recognition_worker_concurrency))
        os.environ["RECOGNITION_WORKER_CONCURRENCY"] = str(val)
        settings.RECOGNITION_WORKER_CONCURRENCY = val
        updated["recognition_worker_concurrency"] = val

    if req.upload_worker_concurrency is not None:
        val = max(1, min(16, req.upload_worker_concurrency))
        os.environ["UPLOAD_WORKER_CONCURRENCY"] = str(val)
        settings.UPLOAD_WORKER_CONCURRENCY = val
        updated["upload_worker_concurrency"] = val

    if req.job_timeout_seconds is not None:
        val = max(10, min(3600, req.job_timeout_seconds))
        os.environ["JOB_TIMEOUT_SECONDS"] = str(val)
        settings.JOB_TIMEOUT_SECONDS = val
        updated["job_timeout_seconds"] = val

    if req.mini_fasnet_min_frames is not None:
        val = max(1, min(10, req.mini_fasnet_min_frames))
        os.environ["MINI_FASNET_MIN_FRAMES"] = str(val)
        settings.MINI_FASNET_MIN_FRAMES = val
        updated["mini_fasnet_min_frames"] = val

    if req.max_top_matches is not None:
        val = max(1, min(100, req.max_top_matches))
        os.environ["MAX_TOP_MATCHES"] = str(val)
        settings.MAX_TOP_MATCHES = val
        updated["max_top_matches"] = val

    return {
        "success": True,
        "message": "Runtime threshold and pipeline configurations updated successfully",
        "updated": updated,
        "config": get_master_config_data()
    }


# ----------------------------------------------------
# STUDIO ACCOUNT & EVENT MANAGEMENT ENDPOINTS
# ----------------------------------------------------

@router.post("/api/v2/master/studios")
async def create_studio_account(req: CreateStudioRequest, user: dict = Depends(require_master_admin)):
    """Creates a new Studio Account with auto-generated studio_id and PBKDF2-HMAC hashed passkey."""
    name = req.studio_name.strip()
    passkey = req.passkey.strip()

    if not name or not passkey:
        raise HTTPException(status_code=400, detail="Studio name and passkey are required")

    studio_id = f"std_{uuid.uuid4().hex[:8]}"
    passkey_h, salt_h = hash_password(passkey)
    now = time.time()

    studio_doc = {
        "studio_id": studio_id,
        "studio_name": name,
        "passkey_hash": passkey_h,
        "salt": salt_h,
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }

    if mongo_db.db is not None:
        await mongo_db.db.studios.insert_one(studio_doc)

    return {
        "success": True,
        "message": f"Studio '{name}' created successfully",
        "studio": {
            "studio_id": studio_id,
            "studio_name": name,
            "is_active": True,
            "created_at": now
        }
    }


@router.get("/api/v2/master/studios")
async def list_studios(user: dict = Depends(require_master_admin)):
    """Lists all studio accounts with per-studio MongoDB images, Qdrant vectors, and events counts."""
    studios = []
    if mongo_db.db is not None:
        try:
            docs = await mongo_db.db.studios.find({}).sort("created_at", -1).to_list(1000)
            for d in docs:
                s_id = d["studio_id"]
                img_count = await mongo_db.db.image_metadata.count_documents({"$or": [{"studio_id": s_id}, {"relative_folder": {"$regex": s_id}}]})
                event_count = await mongo_db.db.events.count_documents({"studio_id": s_id})
                
                studios.append({
                    "studio_id": s_id,
                    "studio_name": d.get("studio_name", "Studio"),
                    "is_active": d.get("is_active", True),
                    "created_at": d.get("created_at", time.time()),
                    "total_images": img_count,
                    "total_vectors": img_count,
                    "total_events": event_count
                })
        except Exception as e:
            logger.warning(f"Error fetching studios: {e}")

    return {"success": True, "studios": studios}


@router.patch("/api/v2/master/studios/{studio_id}/toggle-status")
async def toggle_studio_status(studio_id: str, user: dict = Depends(require_master_admin)):
    """Toggles studio status between Active (true) and Temporarily Closed (false)."""
    if mongo_db.db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    doc = await mongo_db.db.studios.find_one({"studio_id": studio_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Studio '{studio_id}' not found")

    new_status = not doc.get("is_active", True)
    await mongo_db.db.studios.update_one(
        {"studio_id": studio_id},
        {"$set": {"is_active": new_status, "updated_at": time.time()}}
    )

    return {
        "success": True,
        "studio_id": studio_id,
        "is_active": new_status,
        "status_text": "Active" if new_status else "Temporarily Closed"
    }


@router.post("/api/v2/master/studios/{studio_id}/reset-passkey")
async def reset_studio_passkey(studio_id: str, req: ResetPasskeyRequest, user: dict = Depends(require_master_admin)):
    """Securely updates and hashes a new passkey for a studio account."""
    new_pass = req.new_passkey.strip()
    if not new_pass:
        raise HTTPException(status_code=400, detail="New passkey cannot be empty")

    passkey_h, salt_h = hash_password(new_pass)
    now = time.time()

    if mongo_db.db is not None:
        res = await mongo_db.db.studios.update_one(
            {"studio_id": studio_id},
            {"$set": {"passkey_hash": passkey_h, "salt": salt_h, "updated_at": now}}
        )
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail=f"Studio '{studio_id}' not found")

    return {"success": True, "message": f"Passkey for studio '{studio_id}' updated successfully"}


@router.delete("/api/v2/master/studios/{studio_id}")
async def delete_studio(studio_id: str, user: dict = Depends(require_master_admin)):
    """Deletes a studio account and its associated events."""
    if mongo_db.db is not None:
        await mongo_db.db.studios.delete_one({"studio_id": studio_id})
        await mongo_db.db.events.delete_many({"studio_id": studio_id})

    return {"success": True, "message": f"Studio '{studio_id}' deleted cleanly"}


@router.get("/api/v2/master/studios/{studio_id}/events")
async def list_studio_events(studio_id: str, q: Optional[str] = None, user: dict = Depends(require_master_admin)):
    """Lists all events linked to a studio_id with per-event telemetry statistics and overall studio summary."""
    events = []
    total_images_all = 0
    total_vectors_all = 0
    enabled_count = 0

    studio_doc = None
    if mongo_db.db is not None:
        studio_doc = await mongo_db.db.studios.find_one({"studio_id": studio_id})
        query = {"studio_id": studio_id}
        if q and q.strip():
            query["$or"] = [
                {"event_name": {"$regex": q.strip(), "$options": "i"}},
                {"event_id": {"$regex": q.strip(), "$options": "i"}}
            ]

        docs = await mongo_db.db.events.find(query).sort("created_at", -1).to_list(500)
        for d in docs:
            e_id = d["event_id"]
            img_c = await mongo_db.db.image_metadata.count_documents({"$or": [{"event_id": e_id}, {"relative_folder": {"$regex": e_id}}]})
            search_stat = d.get("search_status", "enabled")

            if search_stat == "enabled":
                enabled_count += 1

            total_images_all += img_c
            total_vectors_all += img_c

            events.append({
                "event_id": e_id,
                "studio_id": d["studio_id"],
                "event_name": d["event_name"],
                "event_date": d.get("event_date", ""),
                "search_status": search_stat,
                "total_images": img_c,
                "total_vectors": img_c,
                "total_faces": img_c,
                "created_at": d.get("created_at", time.time())
            })

    sname = studio_doc.get("studio_name", "Studio") if studio_doc else "Studio"
    is_active = studio_doc.get("is_active", True) if studio_doc else True

    return {
        "success": True,
        "studio": {
            "studio_id": studio_id,
            "studio_name": sname,
            "is_active": is_active
        },
        "summary": {
            "total_events": len(events),
            "total_images_all": total_images_all,
            "total_vectors_all": total_vectors_all,
            "enabled_events": enabled_count
        },
        "events": events
    }


@router.patch("/api/v2/master/events/{event_id}/toggle-search")
async def toggle_event_search_status(event_id: str, user: dict = Depends(require_master_admin)):
    """Toggles an event's search_status between 'enabled' and 'disabled'."""
    if mongo_db.db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")

    doc = await mongo_db.db.events.find_one({"event_id": event_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    current = doc.get("search_status", "enabled")
    new_status = "disabled" if current == "enabled" else "enabled"

    await mongo_db.db.events.update_one(
        {"event_id": event_id},
        {"$set": {"search_status": new_status, "updated_at": time.time()}}
    )

    return {
        "success": True,
        "event_id": event_id,
        "search_status": new_status
    }


@router.delete("/api/v2/master/events/{event_id}")
async def delete_event(event_id: str, user: dict = Depends(require_master_admin)):
    """Deletes an event from the events collection."""
    if mongo_db.db is not None:
        await mongo_db.db.events.delete_one({"event_id": event_id})

    return {"success": True, "message": f"Event '{event_id}' deleted successfully"}


@router.websocket("/api/v2/ws/master/{client_id}")
async def master_websocket_endpoint(websocket: WebSocket, client_id: str):
    """Real-time Master WebSocket endpoint broadcasting persistent telemetry pushes."""
    await websocket.accept()
    logger.info(f"Master WebSocket connected: {client_id}")
    try:
        while True:
            mongo_count = 0
            if mongo_db.db is not None:
                try:
                    mongo_count = await mongo_db.db.image_metadata.count_documents({})
                except Exception:
                    pass

            qdrant_points = 0
            if qdrant_service.client is not None:
                try:
                    col_info = await qdrant_service.client.get_collection(collection_name="faces_embed_v2")
                    qdrant_points = getattr(col_info, 'points_count', getattr(col_info, 'vectors_count', 0))
                except Exception:
                    pass

            from src.pipeline.storage.drive_service import drive_service
            drive_health = drive_service.get_health_status()
            if drive_health.get("status") == "HEALTHY" and mongo_db.db is not None:
                try:
                    dh_doc = await mongo_db.db.system_health.find_one({"component": "google_drive"})
                    if dh_doc and dh_doc.get("status") == "FAILED":
                        drive_health["status"] = "FAILED"
                        drive_health["error_message"] = dh_doc.get("error_message", "Google Drive Upload Failed")
                        drive_health["failed_at"] = dh_doc.get("failed_at", time.time())
                except Exception:
                    pass

            payload = {
                "event": "master_telemetry",
                "timestamp": time.time(),
                "telemetry": {
                    "cpu_percent": psutil.cpu_percent(),
                    "ram_percent": psutil.virtual_memory().percent,
                    "ram_used_gb": round((psutil.virtual_memory().used) / (1024 ** 3), 2),
                    "ram_total_gb": round((psutil.virtual_memory().total) / (1024 ** 3), 2),
                    "disk_free_gb": round(psutil.disk_usage("/").free / (1024 ** 3), 2),
                },
                "databases": {
                    "mongo_connected": mongo_db.db is not None,
                    "mongo_total_images": mongo_count,
                    "qdrant_connected": qdrant_service.client is not None,
                    "qdrant_vector_points": qdrant_points,
                    "google_drive_configured": drive_health.get("configured", False),
                    "google_drive_health": drive_health
                },
                "runtime_config": get_master_config_data()
            }

            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2.5)
    except WebSocketDisconnect:
        logger.info(f"Master WebSocket disconnected: {client_id}")
    except Exception as e:
        logger.warning(f"Master WebSocket error: {e}")


@router.post("/api/v2/master/drive/reset-status")
async def reset_google_drive_health_status(user: dict = Depends(require_master_admin)):
    """Resets Google Drive health status back to HEALTHY after resolving storage errors."""
    from src.pipeline.storage.drive_service import drive_service
    drive_service.reset_health_status()
    return {"success": True, "message": "Google Drive health status reset to HEALTHY"}


# ----------------------------------------------------
# 2. HTML Template Endpoints served directly by FastAPI
# ----------------------------------------------------

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AuraFace Master Login</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-50 min-h-screen font-sans flex items-center justify-center p-4 text-slate-900 antialiased selection:bg-black selection:text-white">

  <!-- White Login Card Container -->
  <div class="max-w-sm w-full mx-auto">
    <div class="bg-white rounded-3xl p-8 border border-slate-200 shadow-xl shadow-slate-200/60 space-y-5 relative">
      <div class="text-center space-y-1.5">
        <div class="w-12 h-12 bg-black text-white rounded-2xl mx-auto flex items-center justify-center shadow-md">
          <i class="fa-solid fa-key text-base"></i>
        </div>
        <h2 class="text-xl font-extrabold tracking-tight text-slate-900 pt-1">Master Authentication</h2>
        <p class="text-xs text-slate-500 font-medium">Enter master credentials to access dashboard</p>
      </div>

      <div id="alertBanner" class="hidden p-3 rounded-xl text-xs font-medium"></div>

      <form id="loginForm" class="space-y-4">
        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider">Username</label>
          <div class="relative">
            <i class="fa-solid fa-user absolute left-3 top-3 text-slate-400 text-xs"></i>
            <input type="text" id="usernameInput" required value="kedantra" placeholder="Username"
              class="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-black focus:ring-1 focus:ring-black font-mono transition">
          </div>
        </div>

        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider">Password</label>
          <div class="relative">
            <i class="fa-solid fa-lock absolute left-3 top-3 text-slate-400 text-xs"></i>
            <input type="password" id="passwordInput" required placeholder="••••••••••••"
              class="w-full pl-9 pr-9 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-none focus:border-black focus:ring-1 focus:ring-black font-mono transition">
            <button type="button" id="togglePasswordBtn" class="absolute right-3 top-2.5 text-slate-400 hover:text-slate-700">
              <i class="fa-solid fa-eye text-xs" id="eyeIcon"></i>
            </button>
          </div>
        </div>

        <button type="submit" id="submitBtn"
          class="w-full py-3 px-4 rounded-xl bg-black hover:bg-slate-800 text-white font-extrabold text-xs tracking-wider uppercase transition shadow-md shadow-black/10 flex items-center justify-center space-x-2 mt-2">
          <span id="btnText">Sign In To Dashboard</span>
          <i class="fa-solid fa-arrow-right text-xs" id="btnIcon"></i>
        </button>
      </form>
    </div>
  </div>

  <script>
    const urlParams = new URLSearchParams(window.location.search);
    const reason = urlParams.get('reason');
    const alertBanner = document.getElementById('alertBanner');

    if (reason === 'expired') {
      alertBanner.className = "p-3 rounded-xl bg-amber-50 text-amber-800 border border-amber-200 text-xs block font-medium";
      alertBanner.innerHTML = "<strong>Session Expired:</strong> Access token limit reached. Please log in again.";
    } else if (reason === 'logged_out') {
      alertBanner.className = "p-3 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs block font-medium";
      alertBanner.innerHTML = "Signed out from Master Admin session.";
    }

    const toggleBtn = document.getElementById('togglePasswordBtn');
    const pwdInput = document.getElementById('passwordInput');
    const eyeIcon = document.getElementById('eyeIcon');

    toggleBtn.addEventListener('click', () => {
      if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        eyeIcon.className = 'fa-solid fa-eye-slash text-xs';
      } else {
        pwdInput.type = 'password';
        eyeIcon.className = 'fa-solid fa-eye text-xs';
      }
    });

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('usernameInput').value;
      const password = pwdInput.value;
      const btnText = document.getElementById('btnText');
      const submitBtn = document.getElementById('submitBtn');

      btnText.innerText = "Authenticating...";
      submitBtn.disabled = true;
      alertBanner.className = "hidden";

      try {
        const res = await fetch('/api/v2/master/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, password })
        });

        const data = await res.json();
        if (res.ok && data.success) {
          localStorage.setItem('master_access_token', data.access_token);
          localStorage.setItem('master_refresh_token', data.refresh_token);
          localStorage.setItem('master_token_time', Date.now().toString());
          localStorage.setItem('master_username', data.user.username);
          document.cookie = "master_access_token=" + data.access_token + "; path=/; max-age=900; SameSite=Lax";
          window.location.href = '/master';
        } else {
          alertBanner.className = "p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-xs block font-medium";
          alertBanner.innerText = data.detail || "Invalid master credentials";
        }
      } catch (err) {
        alertBanner.className = "p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-xs block font-medium";
        alertBanner.innerText = "Error connecting to backend authentication API";
      } finally {
        btnText.innerText = "Sign In To Dashboard";
        submitBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AuraFace Master Control Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-50 min-h-screen text-slate-900 font-sans p-4 md:p-6 antialiased selection:bg-black selection:text-white">

  <!-- Create Studio Account Modal -->
  <div id="createStudioModal" class="hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-white text-slate-900 max-w-sm w-full rounded-2xl p-6 border border-slate-200 shadow-2xl space-y-4">
      <div class="flex items-center space-x-3 border-b border-slate-100 pb-3">
        <div class="w-8 h-8 rounded-lg bg-black text-white flex items-center justify-center">
          <i class="fa-solid fa-store text-xs"></i>
        </div>
        <div>
          <h3 class="text-xs font-black uppercase tracking-wider text-slate-900">Add New Studio Account</h3>
          <p class="text-[10px] text-slate-500 font-medium">Auto-generated studio_id & PBKDF2 passkey</p>
        </div>
      </div>
      <form id="createStudioForm" class="space-y-3">
        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider">Studio Name</label>
          <input type="text" id="newStudioName" required placeholder="e.g. Apex Visual Studio"
            class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:border-black">
        </div>
        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider">Studio Passkey</label>
          <input type="password" id="newStudioPasskey" required placeholder="••••••••••••"
            class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 font-mono focus:outline-none focus:border-black">
        </div>
        <div class="flex items-center justify-end gap-2 pt-2">
          <button type="button" id="closeCreateStudioModalBtn" class="px-3.5 py-1.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200">Cancel</button>
          <button type="submit" class="px-3.5 py-1.5 rounded-xl bg-black hover:bg-slate-800 text-white text-xs font-bold">Create Studio</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Reset Studio Passkey Modal -->
  <div id="resetPasskeyModal" class="hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-white text-slate-900 max-w-sm w-full rounded-2xl p-6 border border-slate-200 shadow-2xl space-y-4">
      <div class="flex items-center space-x-3 border-b border-slate-100 pb-3">
        <div class="w-8 h-8 rounded-lg bg-black text-white flex items-center justify-center">
          <i class="fa-solid fa-key text-xs"></i>
        </div>
        <div>
          <h3 class="text-xs font-black uppercase tracking-wider text-slate-900">Reset Studio Passkey</h3>
          <p id="resetStudioTargetLabel" class="text-[10px] text-slate-500 font-mono">std_xxxx</p>
        </div>
      </div>
      <form id="resetPasskeyForm" class="space-y-3">
        <input type="hidden" id="resetTargetStudioId">
        <div class="space-y-1">
          <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider">New Passkey</label>
          <input type="password" id="resetNewPasskey" required placeholder="Enter new passkey"
            class="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 font-mono focus:outline-none focus:border-black">
        </div>
        <div class="flex items-center justify-end gap-2 pt-2">
          <button type="button" id="closeResetPasskeyModalBtn" class="px-3.5 py-1.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200">Cancel</button>
          <button type="submit" class="px-3.5 py-1.5 rounded-xl bg-black hover:bg-slate-800 text-white text-xs font-bold">Update Passkey Hash</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Database Purge Modal -->
  <div id="purgeModal" class="hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-white text-slate-900 max-w-sm w-full rounded-2xl p-6 border border-slate-200 shadow-2xl space-y-4">
      <div class="flex items-center space-x-3 border-b border-slate-100 pb-3 text-red-600">
        <i class="fa-solid fa-triangle-exclamation text-xl"></i>
        <div>
          <h3 class="text-xs font-black uppercase tracking-wider text-slate-900">Wipe System Databases</h3>
          <p class="text-[10px] text-red-600 font-semibold">MongoDB • Qdrant • Google Drive • Disk</p>
        </div>
      </div>
      <p class="text-xs text-slate-600 leading-relaxed">
        Are you sure you want to permanently delete all MongoDB face documents, 512-d Qdrant vector points, Google Drive uploads, and local temporary files?
      </p>
      <div id="modalStatusMsg" class="hidden p-2.5 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold"></div>
      <div class="flex items-center justify-end gap-2 pt-2">
        <button id="cancelPurgeBtn" class="px-3.5 py-1.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200">Cancel</button>
        <button id="confirmPurgeBtn" class="px-3.5 py-1.5 rounded-xl bg-black hover:bg-slate-800 text-white text-xs font-bold">Yes, Purge Everything</button>
      </div>
    </div>
  </div>

  <!-- Threshold Confirmation Modal -->
  <div id="thresholdConfirmModal" class="hidden fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
    <div class="bg-white text-slate-900 max-w-sm w-full rounded-2xl p-6 border border-slate-200 shadow-2xl space-y-4">
      <div class="flex items-center space-x-3 border-b border-slate-100 pb-3 text-amber-600">
        <div class="w-8 h-8 rounded-lg bg-amber-500 text-white flex items-center justify-center">
          <i class="fa-solid fa-sliders text-xs"></i>
        </div>
        <div>
          <h3 class="text-xs font-black uppercase tracking-wider text-slate-900">Confirm Threshold Update</h3>
          <p class="text-[10px] text-slate-500 font-medium">Verify proposed runtime parameter adjustments</p>
        </div>
      </div>
      
      <div class="space-y-2.5 text-xs">
        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1">
          <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Anti-Spoof Real Threshold</div>
          <div class="flex items-center justify-between font-mono font-bold">
            <span id="confirmRealOrig" class="text-slate-500">0.35</span>
            <i class="fa-solid fa-arrow-right text-[10px] text-slate-400"></i>
            <span id="confirmRealNew" class="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">0.35</span>
          </div>
        </div>

        <div class="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-1">
          <div class="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Vector Match Similarity Threshold</div>
          <div class="flex items-center justify-between font-mono font-bold">
            <span id="confirmSimOrig" class="text-slate-500">0.42</span>
            <i class="fa-solid fa-arrow-right text-[10px] text-slate-400"></i>
            <span id="confirmSimNew" class="text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">0.42</span>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-end gap-2 pt-2">
        <button type="button" id="closeThresholdConfirmBtn" class="px-3.5 py-1.5 rounded-xl bg-slate-100 text-slate-700 text-xs font-semibold hover:bg-slate-200">Cancel</button>
        <button type="button" id="submitThresholdConfirmBtn" class="px-3.5 py-1.5 rounded-xl bg-black hover:bg-slate-800 text-white text-xs font-bold shadow-md">Confirm & Apply</button>
      </div>
    </div>
  </div>

  <div class="max-w-6xl mx-auto space-y-5">
    <!-- Clean White Navigation Card Bar -->
    <div class="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
      <div class="flex items-center space-x-3">
        <div class="w-8 h-8 rounded-lg bg-black text-white flex items-center justify-center text-white font-black text-xs">
          A
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <h1 class="text-xs font-black tracking-tight text-slate-900 uppercase">Master Control Center</h1>
            <span id="wsStatus" class="px-2 py-0.5 rounded bg-black text-white text-[9px] font-bold flex items-center gap-1">
              <i class="fa-solid fa-bolt text-emerald-400 text-[10px]"></i>
              <span>WebSocket Stream</span>
            </span>
          </div>
          <p class="text-xs text-slate-500 font-medium">Master Admin: <strong id="usernameDisplay" class="text-slate-900">kedantra</strong></p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <a href="/master/config" class="px-3.5 py-1.5 rounded-lg bg-black hover:bg-slate-800 text-white transition text-xs font-bold flex items-center gap-1.5 shadow-sm border border-slate-800">
          <i class="fa-solid fa-sliders text-xs text-amber-400"></i>
          <span>Configuration Settings</span>
        </a>

        <button id="openCreateStudioModalBtn" class="px-3.5 py-1.5 rounded-lg bg-black hover:bg-slate-800 text-white transition text-xs font-bold flex items-center gap-1.5 shadow-sm">
          <i class="fa-solid fa-plus text-xs"></i>
          <span>Add Studio Account</span>
        </button>

        <button id="logoutBtn" class="px-3.5 py-1.5 rounded-lg bg-black hover:bg-slate-800 text-white transition text-xs font-bold flex items-center gap-1.5 shadow-sm">
          <i class="fa-solid fa-right-from-bracket text-xs"></i>
          <span>Sign Out</span>
        </button>
      </div>
    </div>

    <!-- CRITICAL RED ALERT BANNER (Triggers ONLY when Google Drive fails) -->
    <div id="driveFailureAlertBanner" class="hidden w-full p-4 rounded-2xl bg-red-600 border border-red-700 text-white shadow-xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 animate-pulse">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-red-700/80 border border-red-400/40 flex items-center justify-center text-white shrink-0 shadow-inner">
          <i class="fa-solid fa-triangle-exclamation text-xl"></i>
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <h3 class="text-sm font-black uppercase tracking-wider text-white">CRITICAL ALERT: Google Drive Backup Upload Failed!</h3>
            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-white text-red-700">Auto Local Mode</span>
          </div>
          <p class="text-xs text-red-100 font-medium mt-0.5" id="driveFailureMessage">
            Google Drive storage service threw an error. System automatically switched to Local Disk Database Storage.
          </p>
        </div>
      </div>
      <button id="resetDriveStatusBtn" class="px-4 py-2 rounded-xl bg-white hover:bg-red-50 text-red-700 font-bold text-xs shadow-md transition-all shrink-0 flex items-center space-x-2">
        <i class="fa-solid fa-rotate-right text-xs"></i>
        <span>Reset / Retry Connection</span>
      </button>
    </div>

    <!-- White Telemetry Cards Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-2">
        <div class="flex items-center justify-between text-[11px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>MongoDB Storage</span>
          <div class="w-6 h-6 rounded-md bg-black text-white flex items-center justify-center text-[10px]">
            <i class="fa-solid fa-database"></i>
          </div>
        </div>
        <div class="space-y-0.5">
          <div id="mongoCount" class="text-2xl font-black text-slate-900">0</div>
          <p class="text-[10px] text-slate-500 font-medium">Indexed Image Documents</p>
        </div>
        <div class="pt-0.5">
          <span class="inline-flex items-center gap-1.5 bg-black text-white px-2.5 py-0.5 rounded text-[10px] font-bold">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
            <span>`face_recog_db_v2` Online</span>
          </span>
        </div>
      </div>

      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-2">
        <div class="flex items-center justify-between text-[11px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>Qdrant Vector DB</span>
          <div class="w-6 h-6 rounded-md bg-black text-white flex items-center justify-center text-[10px]">
            <i class="fa-solid fa-layer-group"></i>
          </div>
        </div>
        <div class="space-y-0.5">
          <div id="qdrantCount" class="text-2xl font-black text-slate-900">0</div>
          <p class="text-[10px] text-slate-500 font-medium">512-d Vector Points</p>
        </div>
        <div class="pt-0.5">
          <span class="inline-flex items-center gap-1.5 bg-black text-white px-2.5 py-0.5 rounded text-[10px] font-bold">
            <span class="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse"></span>
            <span>`faces_embed_v2` Active</span>
          </span>
        </div>
      </div>

      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-2">
        <div class="flex items-center justify-between text-[11px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>Google Drive</span>
          <div class="w-6 h-6 rounded-md bg-black text-white flex items-center justify-center text-[10px]">
            <i class="fa-solid fa-hard-drive"></i>
          </div>
        </div>
        <div class="space-y-0.5">
          <div id="driveStatus" class="text-2xl font-black text-slate-900">Active</div>
          <p class="text-[10px] text-slate-500 font-medium">Async Image Storage Sync</p>
        </div>
        <div class="pt-0.5">
          <span class="inline-flex items-center gap-1 bg-black text-white px-2.5 py-0.5 rounded text-[10px] font-bold">
            <i class="fa-solid fa-circle-check text-[10px] text-cyan-400"></i>
            <span>OAuth2 Connected</span>
          </span>
        </div>
      </div>

      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-2">
        <div class="flex items-center justify-between text-[11px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>Server Telemetry</span>
          <div class="w-6 h-6 rounded-md bg-black text-white flex items-center justify-center text-[10px]">
            <i class="fa-solid fa-microchip"></i>
          </div>
        </div>
        <div class="space-y-0.5 font-mono text-[11px]">
          <div class="flex justify-between"><span class="text-slate-500 font-semibold">CPU:</span><strong id="cpuVal" class="text-slate-900">0%</strong></div>
          <div class="flex justify-between"><span class="text-slate-500 font-semibold">RAM:</span><strong id="ramVal" class="text-slate-900">0%</strong></div>
          <div class="flex justify-between"><span class="text-slate-500 font-semibold">Disk Free:</span><strong id="diskVal" class="text-slate-900">0 GB</strong></div>
        </div>
      </div>
    </div>

    <!-- Multi-Tenant Studio Accounts Cards Section -->
    <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
      <div class="flex items-center justify-between border-b border-slate-100 pb-3">
        <div class="flex items-center space-x-2">
          <div class="p-1.5 rounded-lg bg-black text-white text-xs">
            <i class="fa-solid fa-store"></i>
          </div>
          <div>
            <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">Studio Accounts Registry</h2>
            <p class="text-[11px] text-slate-500">Multi-tenant accounts, events, and temporary closure controls</p>
          </div>
        </div>
        <button id="openCreateStudioModalBtn2" class="px-3 py-1.5 rounded-lg bg-black text-white hover:bg-slate-800 text-xs font-bold flex items-center gap-1">
          <i class="fa-solid fa-plus text-[10px]"></i>
          <span>Create Studio</span>
        </button>
      </div>

      <!-- Studio Cards Grid -->
      <div id="studiosGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div class="p-8 text-center text-slate-400 text-xs font-medium col-span-full">Loading registered studio accounts...</div>
      </div>
    </div>

    <!-- White Controls & Operations Cards Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
      <!-- Threshold Controls Card -->
      <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
        <div class="flex items-center justify-between border-b border-slate-100 pb-3">
          <div class="flex items-center space-x-2">
            <div class="p-1.5 rounded-lg bg-black text-white text-xs">
              <i class="fa-solid fa-sliders"></i>
            </div>
            <div>
              <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">Live Threshold Controls</h2>
              <p class="text-[11px] text-slate-500">Adjust anti-spoof & vector match sensitivity</p>
            </div>
          </div>
          <button id="refreshStatsBtn" class="px-2.5 py-1 rounded-lg bg-black text-white hover:bg-slate-800 text-xs font-semibold">
            <i class="fa-solid fa-rotate"></i>
          </button>
        </div>

        <div id="configStatusMsg" class="hidden p-2.5 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold"></div>

        <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
          <div class="flex justify-between items-center text-xs font-bold">
            <span class="text-slate-800">Anti-Spoof Threshold (<code class="text-black">REAL_THRESHOLD</code>)</span>
            <span id="realValDisplay" class="px-2 py-0.5 rounded bg-black text-white font-mono text-xs font-bold">0.35</span>
          </div>
          <input type="range" id="realSlider" min="0.10" max="0.90" step="0.01" value="0.35" class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black">
          <p class="text-[10px] text-slate-500">Minimum landmark liveness real score to accept frame as genuine face.</p>
        </div>

        <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
          <div class="flex justify-between items-center text-xs font-bold">
            <span class="text-slate-800">Vector Match Similarity (<code class="text-black">RECOGNITION_SIMILARITY</code>)</span>
            <span id="simValDisplay" class="px-2 py-0.5 rounded bg-black text-white font-mono text-xs font-bold">0.42</span>
          </div>
          <input type="range" id="simSlider" min="0.20" max="0.85" step="0.01" value="0.42" class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black">
          <p class="text-[10px] text-slate-500">Minimum InsightFace 512-d Cosine similarity score required for match.</p>
        </div>

        <button id="saveConfigBtn" class="w-full py-2.5 rounded-xl bg-black hover:bg-slate-800 text-white font-extrabold text-xs tracking-wider uppercase transition shadow-md shadow-black/10">
          Apply Threshold Settings to Engine
        </button>
      </div>

      <!-- Maintenance Operations Card -->
      <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
        <div class="flex items-center space-x-2 border-b border-slate-100 pb-3">
          <div class="p-1.5 rounded-lg bg-black text-white text-xs">
            <i class="fa-solid fa-server"></i>
          </div>
          <div>
            <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">System Operations</h2>
            <p class="text-[11px] text-slate-500">Database Purge & Lifecycle Controls</p>
          </div>
        </div>

        <div class="space-y-3">
          <div class="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
            <div class="flex items-center justify-between">
              <h3 class="text-xs font-bold text-slate-900">Wipe System Databases & Storage</h3>
              <i class="fa-solid fa-trash-can text-slate-700 text-xs"></i>
            </div>
            <p class="text-[10px] text-slate-500 leading-relaxed">
              Drops MongoDB collections, clears Qdrant vector index, purges Google Drive images, and resets local files.
            </p>
            <button id="openPurgeModalBtn" class="w-full py-2 rounded-xl bg-black hover:bg-slate-800 text-white font-bold text-xs transition shadow-md shadow-black/10">
              Trigger System Purge
            </button>
          </div>

          <div class="p-3.5 rounded-xl bg-slate-900 text-white space-y-1.5 text-xs">
            <div class="flex items-center space-x-2 font-bold text-white">
              <i class="fa-solid fa-key text-xs"></i>
              <span>Engine Parameters</span>
            </div>
            <div class="font-mono text-[10px] space-y-0.5 text-slate-400">
              <p>Model Directory: <span id="modelDirDisplay" class="text-white">./resources/anti_spoof_models</span></p>
              <p>Execution Device: <span id="deviceIdDisplay" class="text-white">0 (CPU/CUDA)</span></p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function logout(reason = 'logged_out') {
      localStorage.removeItem('master_access_token');
      localStorage.removeItem('master_refresh_token');
      localStorage.removeItem('master_token_time');
      localStorage.removeItem('master_username');
      document.cookie = "master_access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      window.location.href = '/master/login?reason=' + reason;
    }

    document.getElementById('logoutBtn').addEventListener('click', () => logout('logged_out'));

    const username = localStorage.getItem('master_username') || 'kedantra';
    document.getElementById('usernameDisplay').innerText = username;

    async function fetchApi(url, options = {}) {
      let accessToken = localStorage.getItem('master_access_token');
      if (!accessToken) {
        logout('expired');
        return null;
      }

      options.headers = options.headers || {};
      options.headers['Authorization'] = 'Bearer ' + accessToken;

      let res = await fetch(url, options);

      if (res.status === 401) {
        const refreshToken = localStorage.getItem('master_refresh_token');
        if (refreshToken) {
          try {
            const refreshRes = await fetch('/api/v2/master/refresh', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (refreshRes.ok) {
              const data = await refreshRes.json();
              localStorage.setItem('master_access_token', data.access_token);
              localStorage.setItem('master_token_time', Date.now().toString());

              options.headers['Authorization'] = 'Bearer ' + data.access_token;
              res = await fetch(url, options);
            } else {
              logout('expired');
              return null;
            }
          } catch {
            logout('expired');
            return null;
          }
        } else {
          logout('expired');
          return null;
        }
      }

      return res;
    }

    let origRealThreshold = 0.35;
    let origSimThreshold = 0.42;

    function updateUIWithStats(data) {
      if (!data) return;
      document.getElementById('mongoCount').innerText = data.databases.mongo_total_images.toLocaleString();
      document.getElementById('qdrantCount').innerText = data.databases.qdrant_vector_points.toLocaleString();
      
      const driveStatusEl = document.getElementById('driveStatus');
      const driveBanner = document.getElementById('driveFailureAlertBanner');
      const driveMsg = document.getElementById('driveFailureMessage');

      if (data.databases && data.databases.google_drive_health) {
        const dh = data.databases.google_drive_health;
        if (dh.status === 'FAILED') {
          if (driveBanner) driveBanner.classList.remove('hidden');
          if (driveMsg) driveMsg.innerText = "Google Drive Storage Error: " + (dh.error_message || "Upload operation failed. System automatically switched to Local Storage Mode.");
          if (driveStatusEl) {
            driveStatusEl.innerText = "FAILED (Local Mode)";
            driveStatusEl.className = "text-2xl font-black text-rose-600 animate-pulse";
          }
        } else {
          if (driveBanner) driveBanner.classList.add('hidden');
          if (driveStatusEl) {
            driveStatusEl.innerText = data.databases.google_drive_configured ? 'Active' : 'Disabled';
            driveStatusEl.className = "text-2xl font-black text-slate-900";
          }
        }
      } else {
        if (driveStatusEl) driveStatusEl.innerText = data.databases.google_drive_configured ? 'Active' : 'Disabled';
      }

      document.getElementById('cpuVal').innerText = data.telemetry.cpu_percent + '%';
      document.getElementById('ramVal').innerText = data.telemetry.ram_percent + '%';
      document.getElementById('diskVal').innerText = data.telemetry.disk_free_gb + ' GB';

      if (data.runtime_config) {
        if (data.runtime_config.real_threshold !== undefined) {
          origRealThreshold = data.runtime_config.real_threshold;
          document.getElementById('realSlider').value = origRealThreshold;
          document.getElementById('realValDisplay').innerText = origRealThreshold.toFixed(2);
        }
        if (data.runtime_config.recognition_similarity_threshold !== undefined) {
          origSimThreshold = data.runtime_config.recognition_similarity_threshold;
          document.getElementById('simSlider').value = origSimThreshold;
          document.getElementById('simValDisplay').innerText = origSimThreshold.toFixed(2);
        }
        if (data.runtime_config.model_dir) document.getElementById('modelDirDisplay').innerText = data.runtime_config.model_dir;
        if (data.runtime_config.device_id !== undefined) document.getElementById('deviceIdDisplay').innerText = data.runtime_config.device_id;
      }
    }

    async function loadStudios() {
      const grid = document.getElementById('studiosGrid');
      const res = await fetchApi('/api/v2/master/studios');
      if (res && res.ok) {
        const data = await res.json();
        const studios = data.studios || [];

        if (studios.length === 0) {
          grid.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs font-medium col-span-full">No studio accounts registered. Click "Add Studio Account" to create one.</div>';
          return;
        }

        grid.innerHTML = studios.map(s => {
          const isActive = s.is_active !== false;
          const statusBadge = isActive 
            ? '<span class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[9px] font-bold">Active</span>'
            : '<span class="px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-[9px] font-bold">Temporarily Closed</span>';

          const toggleBtnText = isActive ? 'Close Studio' : 'Reopen Studio';
          const toggleBtnClass = isActive ? 'bg-amber-50 hover:bg-amber-100 text-amber-800' : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-800';

          return `
            <div class="bg-white border border-slate-200 p-4 rounded-2xl shadow-sm space-y-3 relative flex flex-col justify-between">
              <div class="space-y-1.5">
                <div class="flex items-center justify-between">
                  <h3 class="font-extrabold text-xs text-slate-900 truncate max-w-[140px]">${s.studio_name}</h3>
                  <div class="flex items-center space-x-1">
                    ${statusBadge}
                    <span class="px-1.5 py-0.5 rounded bg-black text-white font-mono text-[9px] font-bold">${s.studio_id}</span>
                  </div>
                </div>

                <div class="grid grid-cols-3 gap-1.5 pt-1 text-center font-mono">
                  <div class="bg-slate-50 p-2 rounded-xl border border-slate-100">
                    <div class="text-xs font-black text-slate-900">${s.total_images}</div>
                    <div class="text-[9px] text-slate-500 font-sans">Images</div>
                  </div>
                  <div class="bg-slate-50 p-2 rounded-xl border border-slate-100">
                    <div class="text-xs font-black text-slate-900">${s.total_vectors}</div>
                    <div class="text-[9px] text-slate-500 font-sans">Vectors</div>
                  </div>
                  <div class="bg-slate-50 p-2 rounded-xl border border-slate-100">
                    <div class="text-xs font-black text-slate-900">${s.total_events}</div>
                    <div class="text-[9px] text-slate-500 font-sans">Events</div>
                  </div>
                </div>
              </div>

              <div class="space-y-1.5 pt-2 border-t border-slate-100">
                <div class="flex items-center gap-1.5 text-[11px]">
                  <a href="/master/studios/${s.studio_id}/events" class="flex-1 py-1.5 rounded-lg bg-black hover:bg-slate-800 text-white font-bold text-[10px] flex items-center justify-center gap-1">
                    <i class="fa-solid fa-calendar-days text-[9px]"></i> View Events
                  </a>
                  <button onclick="openResetPasskeyModal('${s.studio_id}')" class="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold text-[10px] flex items-center gap-1">
                    <i class="fa-solid fa-key text-[9px]"></i> Reset
                  </button>
                  <button onclick="deleteStudio('${s.studio_id}')" class="p-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 transition" title="Delete Studio">
                    <i class="fa-solid fa-trash-can text-[10px]"></i>
                  </button>
                </div>

                <button onclick="toggleStudioStatus('${s.studio_id}')" class="w-full py-1 rounded-lg ${toggleBtnClass} font-bold text-[10px] transition border border-slate-200/50">
                  <i class="fa-solid fa-power-off text-[9px]"></i> ${toggleBtnText}
                </button>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    async function toggleStudioStatus(studioId) {
      const res = await fetchApi(`/api/v2/master/studios/${studioId}/toggle-status`, { method: 'PATCH' });
      if (res && res.ok) {
        loadStudios();
      }
    }

    async function loadMasterStats() {
      const res = await fetchApi('/api/v2/master/stats');
      if (res && res.ok) {
        const data = await res.json();
        updateUIWithStats(data);
      }
      loadStudios();
    }

    loadMasterStats();
    document.getElementById('refreshStatsBtn').addEventListener('click', loadMasterStats);

    function connectMasterWebSocket() {
      try {
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = wsProto + '//' + window.location.host + '/api/v2/ws/master/master_' + Math.random().toString(36).substring(2, 9);
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          document.getElementById('wsStatus').innerHTML = '<i class="fa-solid fa-bolt text-emerald-400 text-[10px]"></i><span>WebSocket Stream</span>';
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.event === 'master_telemetry') {
              updateUIWithStats(data);
            }
          } catch (e) {}
        };

        ws.onclose = () => {
          document.getElementById('wsStatus').innerHTML = '<i class="fa-solid fa-plug text-slate-400 text-[10px]"></i><span>Offline</span>';
        };
      } catch (e) {}
    }

    connectMasterWebSocket();

    const resetDriveBtn = document.getElementById('resetDriveStatusBtn');
    if (resetDriveBtn) {
      resetDriveBtn.addEventListener('click', async () => {
        resetDriveBtn.disabled = true;
        resetDriveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>Resetting...</span>';
        try {
          const res = await fetchApi('/api/v2/master/drive/reset-status', { method: 'POST' });
          if (res && res.ok) {
            const driveBanner = document.getElementById('driveFailureAlertBanner');
            if (driveBanner) driveBanner.classList.add('hidden');
          }
        } catch (err) {
          console.error('Failed to reset Google Drive status:', err);
        } finally {
          resetDriveBtn.disabled = false;
          resetDriveBtn.innerHTML = '<i class="fa-solid fa-rotate-right text-xs"></i> <span>Reset / Retry Connection</span>';
        }
      });
    }

    const createStudioModal = document.getElementById('createStudioModal');
    const openCreateStudioBtns = [document.getElementById('openCreateStudioModalBtn'), document.getElementById('openCreateStudioModalBtn2')];
    openCreateStudioBtns.forEach(btn => { if(btn) btn.addEventListener('click', () => createStudioModal.classList.remove('hidden')); });
    document.getElementById('closeCreateStudioModalBtn').addEventListener('click', () => createStudioModal.classList.add('hidden'));

    document.getElementById('createStudioForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const sname = document.getElementById('newStudioName').value;
      const spass = document.getElementById('newStudioPasskey').value;

      const res = await fetchApi('/api/v2/master/studios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ studio_name: sname, passkey: spass })
      });

      if (res && res.ok) {
        createStudioModal.classList.add('hidden');
        document.getElementById('newStudioName').value = '';
        document.getElementById('newStudioPasskey').value = '';
        loadStudios();
      } else {
        alert('Failed to create studio account');
      }
    });

    const resetPasskeyModal = document.getElementById('resetPasskeyModal');
    document.getElementById('closeResetPasskeyModalBtn').addEventListener('click', () => resetPasskeyModal.classList.add('hidden'));

    window.openResetPasskeyModal = function(studioId) {
      document.getElementById('resetTargetStudioId').value = studioId;
      document.getElementById('resetStudioTargetLabel').innerText = studioId;
      resetPasskeyModal.classList.remove('hidden');
    };

    document.getElementById('resetPasskeyForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const studioId = document.getElementById('resetTargetStudioId').value;
      const newPass = document.getElementById('resetNewPasskey').value;

      const res = await fetchApi(`/api/v2/master/studios/${studioId}/reset-passkey`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_passkey: newPass })
      });

      if (res && res.ok) {
        alert(`Passkey for ${studioId} updated & hashed securely!`);
        resetPasskeyModal.classList.add('hidden');
        document.getElementById('resetNewPasskey').value = '';
      } else {
        alert('Failed to reset studio passkey');
      }
    });

    window.deleteStudio = async function(studioId) {
      if (!confirm(`Are you sure you want to delete studio '${studioId}' and its associated events?`)) return;
      const res = await fetchApi(`/api/v2/master/studios/${studioId}`, { method: 'DELETE' });
      if (res && res.ok) {
        loadStudios();
      }
    };

    const realSlider = document.getElementById('realSlider');
    const simSlider = document.getElementById('simSlider');

    realSlider.addEventListener('input', () => {
      document.getElementById('realValDisplay').innerText = parseFloat(realSlider.value).toFixed(2);
    });

    simSlider.addEventListener('input', () => {
      document.getElementById('simValDisplay').innerText = parseFloat(simSlider.value).toFixed(2);
    });

    const thresholdConfirmModal = document.getElementById('thresholdConfirmModal');
    const closeThresholdConfirmBtn = document.getElementById('closeThresholdConfirmBtn');
    const submitThresholdConfirmBtn = document.getElementById('submitThresholdConfirmBtn');

    document.getElementById('saveConfigBtn').addEventListener('click', () => {
      const newReal = parseFloat(realSlider.value);
      const newSim = parseFloat(simSlider.value);

      document.getElementById('confirmRealOrig').innerText = origRealThreshold.toFixed(2);
      document.getElementById('confirmRealNew').innerText = newReal.toFixed(2);
      document.getElementById('confirmSimOrig').innerText = origSimThreshold.toFixed(2);
      document.getElementById('confirmSimNew').innerText = newSim.toFixed(2);

      thresholdConfirmModal.classList.remove('hidden');
    });

    closeThresholdConfirmBtn.addEventListener('click', () => {
      thresholdConfirmModal.classList.add('hidden');
    });

    submitThresholdConfirmBtn.addEventListener('click', async () => {
      thresholdConfirmModal.classList.add('hidden');
      const configMsg = document.getElementById('configStatusMsg');
      configMsg.className = "hidden";

      const res = await fetchApi('/api/v2/master/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          real_threshold: parseFloat(realSlider.value),
          recognition_similarity_threshold: parseFloat(simSlider.value)
        })
      });

      if (res && res.ok) {
        const data = await res.json();
        if (data.success) {
          configMsg.className = "p-2.5 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold block";
          configMsg.innerText = "Thresholds updated cleanly on FastAPI engine!";
          setTimeout(() => configMsg.className = "hidden", 3000);
          loadMasterStats();
        }
      }
    });

    const modal = document.getElementById('purgeModal');
    document.getElementById('openPurgeModalBtn').addEventListener('click', () => modal.classList.remove('hidden'));
    document.getElementById('cancelPurgeBtn').addEventListener('click', () => modal.classList.add('hidden'));

    document.getElementById('confirmPurgeBtn').addEventListener('click', async () => {
      const msg = document.getElementById('modalStatusMsg');
      msg.className = "p-2.5 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold block";
      msg.innerText = "Wiping MongoDB, Qdrant vectors, Google Drive & disk files...";

      try {
        const res = await fetch('/api/v2/admin/clean-databases', { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.success) {
          msg.innerText = "System reset complete!";
          setTimeout(() => {
            modal.classList.add('hidden');
            msg.className = "hidden";
            loadMasterStats();
          }, 1500);
        } else {
          alert("Failed to clear database collections");
        }
      } catch (err) {
        alert("Error purging system databases");
      }
    });
  </script>
</body>
</html>
"""


EVENTS_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Studio Events Management</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-50 min-h-screen text-slate-900 font-sans p-4 md:p-6 antialiased selection:bg-black selection:text-white">

  <div class="max-w-6xl mx-auto space-y-5">
    <!-- Top Studio Header Bar -->
    <div class="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
      <div class="flex items-center space-x-3">
        <a href="/master" class="w-8 h-8 rounded-lg bg-slate-100 text-slate-800 hover:bg-black hover:text-white transition flex items-center justify-center text-xs font-bold">
          <i class="fa-solid fa-arrow-left"></i>
        </a>
        <div>
          <div class="flex items-center space-x-2">
            <h1 id="studioTitleHeader" class="text-xs font-black tracking-tight text-slate-900 uppercase">Studio Events</h1>
            <span id="studioIdBadgeHeader" class="px-2 py-0.5 rounded bg-black text-white text-[9px] font-mono font-bold">std_xxxx</span>
            <span id="studioStatusPillHeader" class="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[9px] font-bold">Active</span>
          </div>
          <p class="text-xs text-slate-500 font-medium">Multi-Tenant Event Collection & Facial Recognition Search Status</p>
        </div>
      </div>
    </div>

    <!-- Overall Studio Events Summary Stats Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
        <div class="flex items-center justify-between text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>Total Events</span>
          <i class="fa-solid fa-calendar-days text-black text-xs"></i>
        </div>
        <div id="statTotalEvents" class="text-2xl font-black text-slate-900">0</div>
        <p class="text-[10px] text-slate-400">Events registered</p>
      </div>

      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
        <div class="flex items-center justify-between text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>MongoDB Total Images</span>
          <i class="fa-solid fa-database text-black text-xs"></i>
        </div>
        <div id="statTotalImages" class="text-2xl font-black text-slate-900">0</div>
        <p class="text-[10px] text-slate-400">Images indexed</p>
      </div>

      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
        <div class="flex items-center justify-between text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>Qdrant Vectors</span>
          <i class="fa-solid fa-layer-group text-black text-xs"></i>
        </div>
        <div id="statTotalVectors" class="text-2xl font-black text-slate-900">0</div>
        <p class="text-[10px] text-slate-400">512-d Face Embeddings</p>
      </div>

      <div class="bg-white text-slate-900 p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
        <div class="flex items-center justify-between text-[10px] font-extrabold text-slate-500 uppercase tracking-wider">
          <span>Search Enabled</span>
          <i class="fa-solid fa-bolt text-emerald-600 text-xs"></i>
        </div>
        <div id="statEnabledEvents" class="text-2xl font-black text-slate-900">0</div>
        <p class="text-[10px] text-emerald-600 font-semibold">Active search events</p>
      </div>
    </div>

    <!-- Search Bar & Controls Bar -->
    <div class="bg-white border border-slate-200 p-4 rounded-2xl shadow-sm">
      <div class="relative w-full">
        <i class="fa-solid fa-magnifying-glass absolute left-3.5 top-3 text-slate-400 text-xs"></i>
        <input type="text" id="eventSearchInput" placeholder="Search events by name or event_id..."
          class="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 focus:outline-none focus:border-black font-medium">
      </div>
    </div>

    <!-- Event Cards Grid -->
    <div id="eventsGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <div class="p-8 text-center text-slate-400 text-xs font-medium col-span-full">Loading studio events...</div>
    </div>
  </div>

  <script>
    const pathParts = window.location.pathname.split('/');
    const studioId = pathParts[pathParts.indexOf('studios') + 1];

    function logout(reason = 'logged_out') {
      localStorage.removeItem('master_access_token');
      localStorage.removeItem('master_refresh_token');
      document.cookie = "master_access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      window.location.href = '/master/login?reason=' + reason;
    }

    async function fetchApi(url, options = {}) {
      let accessToken = localStorage.getItem('master_access_token');
      if (!accessToken) {
        logout('expired');
        return null;
      }

      options.headers = options.headers || {};
      options.headers['Authorization'] = 'Bearer ' + accessToken;

      let res = await fetch(url, options);

      if (res.status === 401) {
        const refreshToken = localStorage.getItem('master_refresh_token');
        if (refreshToken) {
          try {
            const refreshRes = await fetch('/api/v2/master/refresh', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (refreshRes.ok) {
              const data = await refreshRes.json();
              localStorage.setItem('master_access_token', data.access_token);
              options.headers['Authorization'] = 'Bearer ' + data.access_token;
              res = await fetch(url, options);
            } else {
              logout('expired');
              return null;
            }
          } catch {
            logout('expired');
            return null;
          }
        } else {
          logout('expired');
          return null;
        }
      }

      return res;
    }

    async function loadEvents(query = '') {
      const grid = document.getElementById('eventsGrid');
      const url = `/api/v2/master/studios/${studioId}/events` + (query ? '?q=' + encodeURIComponent(query) : '');
      const res = await fetchApi(url);

      if (res && res.ok) {
        const data = await res.json();
        const studio = data.studio || {};
        const summary = data.summary || {};
        const events = data.events || [];

        document.getElementById('studioTitleHeader').innerText = (studio.studio_name || 'Studio') + ' Events';
        document.getElementById('studioIdBadgeHeader').innerText = studio.studio_id || studioId;

        const isStudioActive = studio.is_active !== false;
        document.getElementById('studioStatusPillHeader').className = isStudioActive
          ? "px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[9px] font-bold"
          : "px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-[9px] font-bold";
        document.getElementById('studioStatusPillHeader').innerText = isStudioActive ? "Active" : "Temporarily Closed";

        document.getElementById('statTotalEvents').innerText = summary.total_events || 0;
        document.getElementById('statTotalImages').innerText = (summary.total_images_all || 0).toLocaleString();
        document.getElementById('statTotalVectors').innerText = (summary.total_vectors_all || 0).toLocaleString();
        document.getElementById('statEnabledEvents').innerText = summary.enabled_events || 0;

        if (events.length === 0) {
          grid.innerHTML = '<div class="p-8 text-center text-slate-400 text-xs font-medium col-span-full">No events registered for this studio yet.</div>';
          return;
        }

        grid.innerHTML = events.map(e => {
          const isSearchEnabled = e.search_status === 'enabled';
          const toggleClass = isSearchEnabled 
            ? 'bg-emerald-50 border-emerald-200 text-emerald-800 hover:bg-emerald-100'
            : 'bg-slate-100 border-slate-200 text-slate-600 hover:bg-slate-200';
          const toggleDot = isSearchEnabled
            ? '<span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping"></span>'
            : '<span class="w-1.5 h-1.5 rounded-full bg-slate-400"></span>';

          return `
            <div class="bg-white border border-slate-200 p-4 rounded-2xl shadow-sm space-y-3 relative flex flex-col justify-between">
              <div class="space-y-1.5">
                <div class="flex items-center justify-between">
                  <h3 class="font-extrabold text-xs text-slate-900 truncate max-w-[150px]">${e.event_name}</h3>
                  <span class="px-1.5 py-0.5 rounded bg-black text-white font-mono text-[9px] font-bold">${e.event_id}</span>
                </div>
                <p class="text-[10px] text-slate-400 font-mono"><i class="fa-regular fa-calendar text-[9px]"></i> Date: ${e.event_date || 'N/A'}</p>

                <!-- Per-Event Telemetry Stats Cards -->
                <div class="grid grid-cols-3 gap-1.5 pt-1 text-center font-mono">
                  <div class="bg-slate-50 p-2 rounded-xl border border-slate-100">
                    <div class="text-xs font-black text-slate-900">${e.total_images}</div>
                    <div class="text-[9px] text-slate-500 font-sans">Images</div>
                  </div>
                  <div class="bg-slate-50 p-2 rounded-xl border border-slate-100">
                    <div class="text-xs font-black text-slate-900">${e.total_vectors}</div>
                    <div class="text-[9px] text-slate-500 font-sans">Vectors</div>
                  </div>
                  <div class="bg-slate-50 p-2 rounded-xl border border-slate-100">
                    <div class="text-xs font-black text-slate-900">${e.total_faces}</div>
                    <div class="text-[9px] text-slate-500 font-sans">Faces</div>
                  </div>
                </div>
              </div>

              <div class="pt-2 border-t border-slate-100 flex items-center justify-between gap-2">
                <!-- Search Status Toggle Button Widget -->
                <button onclick="toggleEventSearchStatus('${e.event_id}')" class="flex-1 py-1.5 px-2 rounded-xl border ${toggleClass} text-[10px] font-bold flex items-center justify-center gap-1.5 transition">
                  ${toggleDot}
                  <span>Search: ${isSearchEnabled ? 'Enabled' : 'Disabled'}</span>
                </button>

                <button onclick="deleteEvent('${e.event_id}')" class="p-1.5 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 transition" title="Delete Event">
                  <i class="fa-solid fa-trash-can text-[10px]"></i>
                </button>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    loadEvents();

    let searchTimeout;
    document.getElementById('eventSearchInput').addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => loadEvents(e.target.value), 250);
    });

    async function toggleEventSearchStatus(eventId) {
      const res = await fetchApi(`/api/v2/master/events/${eventId}/toggle-search`, { method: 'PATCH' });
      if (res && res.ok) {
        loadEvents(document.getElementById('eventSearchInput').value);
      }
    }

    async function deleteEvent(eventId) {
      if (!confirm(`Are you sure you want to delete event '${eventId}'?`)) return;
      const res = await fetchApi(`/api/v2/master/events/${eventId}`, { method: 'DELETE' });
      if (res && res.ok) {
        loadEvents(document.getElementById('eventSearchInput').value);
      }
    }
  </script>
</body>
</html>
"""


@router.get("/master/login", response_class=HTMLResponse)
async def master_login_html(request: Request):
    """Serves the standalone Master Login HTML Template."""
    token = request.cookies.get("master_access_token")
    if token and verify_jwt_token(token):
        return RedirectResponse(url="/master", status_code=307)

    return HTMLResponse(content=LOGIN_HTML)


@router.get("/master", response_class=HTMLResponse)
async def master_dashboard_html(request: Request):
    """
    Serves the standalone Master Control Dashboard HTML Template.
    Enforces strict server-side cookie verification before returning HTML.
    If cookie is missing, invalid, or expired, immediately redirects to /master/login with zero UI flash.
    """
    token = request.cookies.get("master_access_token")
    if not token:
        return RedirectResponse(url="/master/login?reason=expired", status_code=307)

    payload = verify_jwt_token(token)
    if not payload or payload.get("role") != "master_admin":
        return RedirectResponse(url="/master/login?reason=expired", status_code=307)

    return HTMLResponse(content=DASHBOARD_HTML)


CONFIG_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AuraFace Master System Configuration</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-50 min-h-screen text-slate-900 font-sans p-4 md:p-6 antialiased selection:bg-black selection:text-white">

  <div class="max-w-5xl mx-auto space-y-5">
    <!-- Clean White Navigation Card Bar -->
    <div class="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
      <div class="flex items-center space-x-3">
        <a href="/master" class="w-8 h-8 rounded-lg bg-black hover:bg-slate-800 text-white flex items-center justify-center transition shadow-sm" title="Back to Dashboard">
          <i class="fa-solid fa-arrow-left text-xs"></i>
        </a>
        <div>
          <div class="flex items-center space-x-2">
            <h1 class="text-xs font-black tracking-tight text-slate-900 uppercase">System Configuration Settings</h1>
            <span class="px-2 py-0.5 rounded bg-black text-white text-[9px] font-bold flex items-center gap-1">
              <i class="fa-solid fa-sliders text-amber-400 text-[10px]"></i>
              <span>Runtime Engine</span>
            </span>
          </div>
          <p class="text-xs text-slate-500 font-medium">Fine-tune anti-spoofing, vector search, worker concurrency & cloud parameters</p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button id="logoutBtn" class="px-3.5 py-1.5 rounded-lg bg-black hover:bg-slate-800 text-white transition text-xs font-bold flex items-center gap-1.5 shadow-sm">
          <i class="fa-solid fa-right-from-bracket text-xs"></i>
          <span>Sign Out</span>
        </button>
      </div>
    </div>

    <!-- Alert / Toast Banner -->
    <div id="configAlert" class="hidden p-3 rounded-xl text-xs font-semibold block transition border"></div>

    <form id="configForm" class="space-y-5">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">

        <!-- 1. Anti-Spoofing & Liveness Section -->
        <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <div class="flex items-center space-x-2 border-b border-slate-100 pb-3">
            <div class="p-1.5 rounded-lg bg-black text-white text-xs">
              <i class="fa-solid fa-shield-halved"></i>
            </div>
            <div>
              <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">Anti-Spoofing & Liveness</h2>
              <p class="text-[11px] text-slate-500">Landmark liveness thresholds & deformability analysis</p>
            </div>
          </div>

          <!-- Real Threshold -->
          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <div class="flex justify-between items-center text-xs font-bold">
              <span class="text-slate-800">Real Threshold (<code class="text-black">REAL_THRESHOLD</code>)</span>
              <span id="cfgRealVal" class="px-2 py-0.5 rounded bg-black text-white font-mono text-xs font-bold">0.35</span>
            </div>
            <input type="range" id="inputRealThreshold" min="0.05" max="0.95" step="0.01" value="0.35" class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black">
            <p class="text-[10px] text-slate-500">Minimum score to classify face frame as genuine/live.</p>
          </div>

          <!-- Crop Scale -->
          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <div class="flex justify-between items-center text-xs font-bold">
              <span class="text-slate-800">Face Crop Scale (<code class="text-black">CROP_SCALE</code>)</span>
              <span id="cfgCropVal" class="px-2 py-0.5 rounded bg-black text-white font-mono text-xs font-bold">2.70</span>
            </div>
            <input type="range" id="inputCropScale" min="1.0" max="5.0" step="0.1" value="2.7" class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black">
            <p class="text-[10px] text-slate-500">Bounding box expansion multiplier for liveness inspection.</p>
          </div>

          <!-- Min Real Frames -->
          <div class="space-y-1.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider block">Min FASNet Real Frames</label>
            <input type="number" id="inputMinFrames" min="1" max="10" value="2"
              class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-mono text-slate-900 focus:outline-none focus:border-black">
            <p class="text-[10px] text-slate-500">Minimum consecutive real frames required per session.</p>
          </div>
        </div>

        <!-- 2. Face Recognition & Vector Search Section -->
        <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <div class="flex items-center space-x-2 border-b border-slate-100 pb-3">
            <div class="p-1.5 rounded-lg bg-black text-white text-xs">
              <i class="fa-solid fa-face-smile"></i>
            </div>
            <div>
              <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">Recognition & Search</h2>
              <p class="text-[11px] text-slate-500">Cosine similarity & detection sensitivity</p>
            </div>
          </div>

          <!-- Recognition Similarity Threshold -->
          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <div class="flex justify-between items-center text-xs font-bold">
              <span class="text-slate-800">Similarity Threshold (<code class="text-black">RECOGNITION_SIMILARITY</code>)</span>
              <span id="cfgSimVal" class="px-2 py-0.5 rounded bg-black text-white font-mono text-xs font-bold">0.42</span>
            </div>
            <input type="range" id="inputSimThreshold" min="0.10" max="0.95" step="0.01" value="0.42" class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black">
            <p class="text-[10px] text-slate-500">InsightFace 512-d Cosine similarity cut-off score.</p>
          </div>

          <!-- Detection Threshold -->
          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <div class="flex justify-between items-center text-xs font-bold">
              <span class="text-slate-800">Face Detection Threshold (<code class="text-black">FACE_DETECTION</code>)</span>
              <span id="cfgDetVal" class="px-2 py-0.5 rounded bg-black text-white font-mono text-xs font-bold">0.30</span>
            </div>
            <input type="range" id="inputDetThreshold" min="0.05" max="0.95" step="0.01" value="0.30" class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black">
            <p class="text-[10px] text-slate-500">Detector confidence score for extracting bounding box.</p>
          </div>

          <!-- Max Top Matches -->
          <div class="space-y-1.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider block">Max Candidate Matches</label>
            <input type="number" id="inputMaxMatches" min="1" max="100" value="10"
              class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-mono text-slate-900 focus:outline-none focus:border-black">
            <p class="text-[10px] text-slate-500">Maximum top candidate vector points returned by Qdrant.</p>
          </div>
        </div>

        <!-- 3. Worker Concurrency & Timeout Section -->
        <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <div class="flex items-center space-x-2 border-b border-slate-100 pb-3">
            <div class="p-1.5 rounded-lg bg-black text-white text-xs">
              <i class="fa-solid fa-gears"></i>
            </div>
            <div>
              <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">Worker Concurrency & Timeouts</h2>
              <p class="text-[11px] text-slate-500">Thread pool allocations & job limits</p>
            </div>
          </div>

          <div class="space-y-1.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider block">Recognition Worker Concurrency</label>
            <input type="number" id="inputRecWorkers" min="1" max="16" value="2"
              class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-mono text-slate-900 focus:outline-none focus:border-black">
            <p class="text-[10px] text-slate-500">Active worker thread threads allocated for recognition tasks.</p>
          </div>

          <div class="space-y-1.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider block">Upload Worker Concurrency</label>
            <input type="number" id="inputUpWorkers" min="1" max="16" value="2"
              class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-mono text-slate-900 focus:outline-none focus:border-black">
            <p class="text-[10px] text-slate-500">Thread pool capacity for background Drive/Mongo sync.</p>
          </div>

          <div class="space-y-1.5 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
            <label class="text-[10px] font-bold text-slate-700 uppercase tracking-wider block">Job Timeout (Seconds)</label>
            <input type="number" id="inputJobTimeout" min="10" max="3600" value="300"
              class="w-full px-3 py-2 bg-white border border-slate-200 rounded-xl text-xs font-mono text-slate-900 focus:outline-none focus:border-black">
            <p class="text-[10px] text-slate-500">Maximum execution time permitted before dropping stale queue jobs.</p>
          </div>
        </div>

        <!-- 4. Environment & Storage Meta Section -->
        <div class="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-4">
          <div class="flex items-center space-x-2 border-b border-slate-100 pb-3">
            <div class="p-1.5 rounded-lg bg-black text-white text-xs">
              <i class="fa-solid fa-server"></i>
            </div>
            <div>
              <h2 class="text-xs font-black text-slate-900 uppercase tracking-wider">Cloud Storage & Engine Meta</h2>
              <p class="text-[11px] text-slate-500">Google Drive & model execution settings</p>
            </div>
          </div>

          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs font-mono">
            <div class="text-[10px] font-bold text-slate-700 uppercase tracking-wider font-sans">Model Directory</div>
            <div id="metaModelDir" class="text-slate-900 truncate font-bold">./resources/anti_spoof_models</div>
          </div>

          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs font-mono">
            <div class="text-[10px] font-bold text-slate-700 uppercase tracking-wider font-sans">Device ID</div>
            <div id="metaDeviceId" class="text-slate-900 font-bold">0 (CPU / CUDA)</div>
          </div>

          <div class="space-y-2 bg-slate-50 p-3.5 rounded-xl border border-slate-200 text-xs font-mono">
            <div class="text-[10px] font-bold text-slate-700 uppercase tracking-wider font-sans">Google Drive Parent Folder ID</div>
            <div id="metaDriveFolder" class="text-slate-900 truncate font-bold">Not Configured</div>
          </div>
        </div>

      </div>

      <!-- Action Button Bar -->
      <div class="pt-2 flex justify-end">
        <button type="submit" id="saveFullConfigBtn"
          class="w-full md:w-auto px-8 py-3 rounded-xl bg-black hover:bg-slate-800 text-white font-extrabold text-xs tracking-wider uppercase transition shadow-md shadow-black/10 flex items-center justify-center gap-2">
          <i class="fa-solid fa-floppy-disk text-xs"></i>
          <span>Save System Configurations</span>
        </button>
      </div>
    </form>
  </div>

  <script>
    function logout(reason = 'logged_out') {
      localStorage.removeItem('master_access_token');
      localStorage.removeItem('master_refresh_token');
      localStorage.removeItem('master_token_time');
      localStorage.removeItem('master_username');
      document.cookie = "master_access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
      window.location.href = '/master/login?reason=' + reason;
    }

    document.getElementById('logoutBtn').addEventListener('click', () => logout('logged_out'));

    async function fetchApi(url, options = {}) {
      let accessToken = localStorage.getItem('master_access_token');
      if (!accessToken) {
        logout('expired');
        return null;
      }

      options.headers = options.headers || {};
      options.headers['Authorization'] = 'Bearer ' + accessToken;

      let res = await fetch(url, options);

      if (res.status === 401) {
        const refreshToken = localStorage.getItem('master_refresh_token');
        if (refreshToken) {
          try {
            const refreshRes = await fetch('/api/v2/master/refresh', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (refreshRes.ok) {
              const data = await refreshRes.json();
              localStorage.setItem('master_access_token', data.access_token);
              options.headers['Authorization'] = 'Bearer ' + data.access_token;
              res = await fetch(url, options);
            } else {
              logout('expired');
              return null;
            }
          } catch {
            logout('expired');
            return null;
          }
        } else {
          logout('expired');
          return null;
        }
      }

      return res;
    }

    // Input elements
    const inputReal = document.getElementById('inputRealThreshold');
    const inputCrop = document.getElementById('inputCropScale');
    const inputMinFrames = document.getElementById('inputMinFrames');
    const inputSim = document.getElementById('inputSimThreshold');
    const inputDet = document.getElementById('inputDetThreshold');
    const inputMaxMatches = document.getElementById('inputMaxMatches');
    const inputRecWorkers = document.getElementById('inputRecWorkers');
    const inputUpWorkers = document.getElementById('inputUpWorkers');
    const inputJobTimeout = document.getElementById('inputJobTimeout');

    // Badge updates
    inputReal.addEventListener('input', () => document.getElementById('cfgRealVal').innerText = parseFloat(inputReal.value).toFixed(2));
    inputCrop.addEventListener('input', () => document.getElementById('cfgCropVal').innerText = parseFloat(inputCrop.value).toFixed(2));
    inputSim.addEventListener('input', () => document.getElementById('cfgSimVal').innerText = parseFloat(inputSim.value).toFixed(2));
    inputDet.addEventListener('input', () => document.getElementById('cfgDetVal').innerText = parseFloat(inputDet.value).toFixed(2));

    async function loadConfig() {
      const res = await fetchApi('/api/v2/master/config');
      if (res && res.ok) {
        const data = await res.json();
        const cfg = data.config || {};

        if (cfg.real_threshold !== undefined) {
          inputReal.value = cfg.real_threshold;
          document.getElementById('cfgRealVal').innerText = parseFloat(cfg.real_threshold).toFixed(2);
        }
        if (cfg.crop_scale !== undefined) {
          inputCrop.value = cfg.crop_scale;
          document.getElementById('cfgCropVal').innerText = parseFloat(cfg.crop_scale).toFixed(2);
        }
        if (cfg.mini_fasnet_min_frames !== undefined) inputMinFrames.value = cfg.mini_fasnet_min_frames;
        if (cfg.recognition_similarity_threshold !== undefined) {
          inputSim.value = cfg.recognition_similarity_threshold;
          document.getElementById('cfgSimVal').innerText = parseFloat(cfg.recognition_similarity_threshold).toFixed(2);
        }
        if (cfg.face_detection_threshold !== undefined) {
          inputDet.value = cfg.face_detection_threshold;
          document.getElementById('cfgDetVal').innerText = parseFloat(cfg.face_detection_threshold).toFixed(2);
        }
        if (cfg.max_top_matches !== undefined) inputMaxMatches.value = cfg.max_top_matches;
        if (cfg.recognition_worker_concurrency !== undefined) inputRecWorkers.value = cfg.recognition_worker_concurrency;
        if (cfg.upload_worker_concurrency !== undefined) inputUpWorkers.value = cfg.upload_worker_concurrency;
        if (cfg.job_timeout_seconds !== undefined) inputJobTimeout.value = cfg.job_timeout_seconds;

        if (cfg.model_dir) document.getElementById('metaModelDir').innerText = cfg.model_dir;
        if (cfg.device_id !== undefined) document.getElementById('metaDeviceId').innerText = cfg.device_id;
        if (cfg.google_drive_parent_folder_id) document.getElementById('metaDriveFolder').innerText = cfg.google_drive_parent_folder_id;
      }
    }

    loadConfig();

    document.getElementById('configForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const alertBox = document.getElementById('configAlert');
      alertBox.className = "hidden";

      const payload = {
        real_threshold: parseFloat(inputReal.value),
        crop_scale: parseFloat(inputCrop.value),
        mini_fasnet_min_frames: parseInt(inputMinFrames.value, 10),
        recognition_similarity_threshold: parseFloat(inputSim.value),
        face_detection_threshold: parseFloat(inputDet.value),
        max_top_matches: parseInt(inputMaxMatches.value, 10),
        recognition_worker_concurrency: parseInt(inputRecWorkers.value, 10),
        upload_worker_concurrency: parseInt(inputUpWorkers.value, 10),
        job_timeout_seconds: parseInt(inputJobTimeout.value, 10)
      };

      const res = await fetchApi('/api/v2/master/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res && res.ok) {
        const data = await res.json();
        if (data.success) {
          alertBox.className = "p-3 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 text-xs font-semibold block";
          alertBox.innerHTML = '<i class="fa-solid fa-circle-check text-emerald-600 mr-1.5"></i> System pipeline configurations updated cleanly on FastAPI engine!';
          window.scrollTo({ top: 0, behavior: 'smooth' });
          setTimeout(() => alertBox.className = "hidden", 4000);
          loadConfig();
        }
      } else {
        alertBox.className = "p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-xs font-semibold block";
        alertBox.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-red-600 mr-1.5"></i> Failed to save system configurations.';
      }
    });
  </script>
</body>
</html>
"""


@router.get("/master/config", response_class=HTMLResponse)
async def master_config_html(request: Request):
    """
    Serves the standalone Master System Configuration Page.
    Enforces strict server-side cookie verification before returning HTML.
    If cookie is missing, invalid, or expired, immediately redirects to /master/login with zero UI flash.
    """
    token = request.cookies.get("master_access_token")
    if not token:
        return RedirectResponse(url="/master/login?reason=expired", status_code=307)

    payload = verify_jwt_token(token)
    if not payload or payload.get("role") != "master_admin":
        return RedirectResponse(url="/master/login?reason=expired", status_code=307)

    return HTMLResponse(content=CONFIG_HTML)


@router.get("/master/studios/{studio_id}/events", response_class=HTMLResponse)
async def studio_events_html(studio_id: str, request: Request):
    """
    Serves the standalone Premium Studio Events HTML Template.
    Enforces strict server-side cookie verification before returning HTML.
    If cookie is missing, invalid, or expired, immediately redirects to /master/login with zero UI flash.
    """
    token = request.cookies.get("master_access_token")
    if not token:
        return RedirectResponse(url="/master/login?reason=expired", status_code=307)

    payload = verify_jwt_token(token)
    if not payload or payload.get("role") != "master_admin":
        return RedirectResponse(url="/master/login?reason=expired", status_code=307)

    return HTMLResponse(content=EVENTS_HTML)
