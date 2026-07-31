# -*- coding: utf-8 -*-
"""
Google Drive Asynchronous Storage Service
-----------------------------------------
Uploads original uncompressed images to Google Drive using Google OAuth2 Refresh Token.
Handles automatic token refresh, resumable upload sessions, and exponential retries.
"""

import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any
from src.pipeline.config import settings

logger = logging.getLogger("pipeline.drive")

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    logger.warning("Google Drive SDK not installed. Drive uploads will run in mock/local mode.")


class GoogleDriveService:
    def __init__(self):
        self.service = None
        self.parent_folder_id = settings.GOOGLE_DRIVE_PARENT_FOLDER_ID
        self._init_service()

    def _init_service(self):
        if not GOOGLE_DRIVE_AVAILABLE:
            return

        try:
            if settings.GOOGLE_DRIVE_REFRESH_TOKEN and settings.GOOGLE_DRIVE_CLIENT_ID:
                creds = Credentials(
                    token=None,
                    refresh_token=settings.GOOGLE_DRIVE_REFRESH_TOKEN,
                    client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
                    client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET,
                    token_uri="https://oauth2.googleapis.com/token"
                )
                self.service = build("drive", "v3", credentials=creds)
                logger.info("Google Drive service client initialized successfully.")
            else:
                logger.info("Google Drive credentials omitted. Async Drive upload disabled.")
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive service: {e}")
            self.service = None

    async def upload_file(self, file_path: str, filename: str, mime_type: str = "image/jpeg") -> Optional[Dict[str, str]]:
        """
        Asynchronously uploads an original image file to Google Drive with retries.
        Returns dict containing drive_file_id and drive_url.
        """
        if not self.service or not os.path.exists(file_path):
            # Fallback mock drive response if drive is not configured
            return {
                "drive_file_id": f"local_{int(time.time())}",
                "drive_url": f"file://{os.path.abspath(file_path)}"
            }

        max_retries = 3
        backoff = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                # Execute in executor thread to prevent blocking asyncio loop
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self._execute_upload,
                    file_path,
                    filename,
                    mime_type
                )
                return result
            except Exception as e:
                logger.warning(f"Google Drive upload attempt {attempt} failed for {filename}: {e}")
                if attempt == max_retries:
                    logger.error(f"Google Drive upload permanently failed for {filename}")
                    raise e
                await asyncio.sleep(backoff)
                backoff *= 2.0

        return None

    def _execute_upload(self, file_path: str, filename: str, mime_type: str) -> Dict[str, str]:
        file_metadata = {
            "name": filename,
        }
        if self.parent_folder_id:
            file_metadata["parents"] = [self.parent_folder_id]

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        drive_file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink, webContentLink"
        ).execute()

        return {
            "drive_file_id": drive_file.get("id"),
            "drive_url": drive_file.get("webViewLink") or drive_file.get("webContentLink") or f"https://drive.google.com/file/d/{drive_file.get('id')}/view"
        }


drive_service = GoogleDriveService()
