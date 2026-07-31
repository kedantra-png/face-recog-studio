# -*- coding: utf-8 -*-
"""
Security Service Module
-----------------------
Enterprise-grade security engine for the Face Recognition Gateway:
1. Short-lived session token issuance & validation.
2. HMAC-SHA256 request signature verification.
3. Timestamp drift validation & Nonce replay protection.
4. Sliding-window rate limiting per IP / Session.
5. Frame structure, MIME, resolution, and JPEG byte integrity validation.
6. Security audit logging for unauthorized or spoof attempts.
"""

import time
import hmac
import hashlib
import uuid
import secrets
import logging
import cv2
import numpy as np
from typing import Dict, Any, Tuple, Optional, List
from collections import defaultdict

from src.pipeline.config import settings
from src.pipeline.db.mongo import mongo_db

logger = logging.getLogger("pipeline.security")


class SecurityService:
    def __init__(self):
        self.secret_key = settings.RECOGNITION_SECRET_KEY.encode('utf-8')
        # In-memory fast cache for nonces: nonce -> expiration_timestamp
        self._nonce_cache: Dict[str, float] = {}
        # In-memory sliding window rate limiter: client_ip -> list of timestamps
        self._rate_limiter: Dict[str, List[float]] = defaultdict(list)

    def create_recognition_session(self, client_ip: str) -> Dict[str, Any]:
        """
        Creates a short-lived (60s) recognition session token and client secret.
        """
        session_id = f"sec_sess_{uuid.uuid4().hex[:16]}"
        client_secret = secrets.token_hex(16)
        created_at = time.time()
        expires_at = created_at + settings.SESSION_TTL_SECONDS
        nonce = secrets.token_hex(8)

        session_data = {
            "session_id": session_id,
            "client_secret": client_secret,
            "client_ip": client_ip,
            "created_at": created_at,
            "expires_at": expires_at,
            "nonce": nonce,
            "used": False
        }

        logger.info(f"Generated secure recognition session: {session_id} for IP {client_ip}")
        return session_data

    def check_rate_limit(self, client_ip: str) -> Tuple[bool, str]:
        """
        Sliding-window rate limiter. Returns (is_allowed, error_msg).
        """
        now = time.time()
        window_start = now - 60.0

        # Purge timestamps older than 60s
        timestamps = [t for t in self._rate_limiter[client_ip] if t > window_start]
        self._rate_limiter[client_ip] = timestamps

        if len(timestamps) >= settings.RATE_LIMIT_RPM:
            msg = f"Rate limit exceeded ({len(timestamps)} requests/min). Max allowed is {settings.RATE_LIMIT_RPM} RPM."
            logger.warning(f"Rate limit hit for IP {client_ip}: {msg}")
            return False, msg

        self._rate_limiter[client_ip].append(now)
        return True, ""

    def validate_nonce_and_timestamp(self, timestamp: float, nonce: str) -> Tuple[bool, str]:
        """
        Verifies timestamp freshness and ensures nonce has not been replayed.
        """
        now = time.time()
        # 1. Check timestamp drift
        drift = abs(now - timestamp)
        if drift > settings.MAX_FRAME_AGE_SECONDS:
            return False, f"Request timestamp expired (drift: {round(drift, 1)}s, max: {settings.MAX_FRAME_AGE_SECONDS}s)"

        # 2. Purge expired nonces
        self._purge_expired_nonces(now)

        # 3. Check for replay attack
        if nonce in self._nonce_cache:
            return False, f"Replay attack detected: Nonce '{nonce}' has already been processed"

        # Register nonce with expiration
        self._nonce_cache[nonce] = now + settings.REPLAY_NONCE_TTL_SECONDS
        return True, ""

    def compute_signature(self, session_id: str, timestamp: float, nonce: str, payload_bytes_hash: str) -> str:
        """
        Computes HMAC-SHA256 signature over session_id + timestamp + nonce + payload_hash.
        """
        msg = f"{session_id}:{timestamp}:{nonce}:{payload_bytes_hash}".encode('utf-8')
        return hmac.new(self.secret_key, msg, hashlib.sha256).hexdigest()

    def verify_signature(
        self,
        session_id: str,
        timestamp: float,
        nonce: str,
        payload_bytes_hash: str,
        provided_signature: str
    ) -> bool:
        """
        Validates HMAC-SHA256 signature in constant time.
        """
        expected_signature = self.compute_signature(session_id, timestamp, nonce, payload_bytes_hash)
        return hmac.compare_digest(expected_signature, provided_signature)

    def validate_image_integrity(self, image_bytes: bytes) -> Tuple[bool, Optional[np.ndarray], str]:
        """
        Validates frame payload structure, JPEG header/footer integrity, resolution, and corruption.
        """
        if not image_bytes or len(image_bytes) < 100:
            return False, None, "Invalid image payload: Bytes empty or too short (<100 bytes)"

        # JPEG magic header & EOI footer check
        is_jpeg = image_bytes.startswith(b'\xff\xd8') and (b'\xff\xd9' in image_bytes[-10:])
        is_png = image_bytes.startswith(b'\x89PNG\r\n\x1a\n')
        is_webp = image_bytes[0:4] == b'RIFF' and image_bytes[8:12] == b'WEBP'

        if not (is_jpeg or is_png or is_webp):
            return False, None, "Invalid image structure: File format must be valid JPEG, PNG, or WebP"

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None or img.size == 0:
                return False, None, "Corrupted image bytes: OpenCV failed to decode frame"

            h, w, c = img.shape
            if h < 120 or w < 120:
                return False, None, f"Frame resolution too low ({w}x{h}px). Minimum required is 120x120px."

            if h > 4096 or w > 4096:
                return False, None, f"Frame resolution exceeds maximum allowed dimensions ({w}x{h}px)."

            return True, img, "Image integrity validated successfully"

        except Exception as e:
            return False, None, f"Corrupted image payload: {str(e)}"

    async def log_security_event(
        self,
        event_type: str,
        client_ip: str,
        session_id: Optional[str],
        details: Dict[str, Any]
    ):
        """
        Logs security violation or audit event to MongoDB and logging output.
        """
        audit_doc = {
            "event_type": event_type,
            "client_ip": client_ip,
            "session_id": session_id,
            "timestamp": time.time(),
            "details": details
        }
        logger.warning(f"SECURITY AUDIT EVENT [{event_type}] from IP {client_ip} (session {session_id}): {details.get('message', '')}")
        if mongo_db.db is not None:
            try:
                await mongo_db.db.audit_logs.insert_one(audit_doc)
            except Exception as e:
                logger.error(f"Failed to persist security audit event to MongoDB: {e}")

    def _purge_expired_nonces(self, now: float):
        expired = [n for n, exp in self._nonce_cache.items() if exp < now]
        for n in expired:
            del self._nonce_cache[n]


security_service = SecurityService()
