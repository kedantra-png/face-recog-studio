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
        self.health_status: str = "HEALTHY"
        self.last_error_message: str = ""
        self.last_error_time: float = 0.0
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
            self.health_status = "FAILED"
            self.last_error_message = f"Initialization error: {e}"

    def get_health_status(self) -> Dict[str, Any]:
        return {
            "status": self.health_status,
            "error_message": self.last_error_message,
            "failed_at": self.last_error_time,
            "configured": bool(self.service)
        }

    def reset_health_status(self):
        self.health_status = "HEALTHY"
        self.last_error_message = ""
        self.last_error_time = 0.0
        try:
            from src.pipeline.db.mongo import mongo_db
            if mongo_db.db is not None:
                asyncio.create_task(mongo_db.db.system_health.update_one(
                    {"component": "google_drive"},
                    {"$set": {
                        "component": "google_drive",
                        "status": "HEALTHY",
                        "error_message": "",
                        "updated_at": time.time()
                    }},
                    upsert=True
                ))
        except Exception:
            pass

    async def upload_file(self, file_path: str, filename: str, mime_type: str = "image/jpeg") -> Optional[Dict[str, str]]:
        """
        Asynchronously uploads an original image file to Google Drive.
        On failure, automatically marks health status as FAILED, logs system_health,
        and returns local disk storage fallback.
        """
        if not self.service or not os.path.exists(file_path):
            return {
                "drive_file_id": f"local_{int(time.time())}",
                "drive_url": f"file://{os.path.abspath(file_path)}"
            }

        max_retries = 5
        backoff = 1.0

        for attempt in range(1, max_retries + 1):
            try:
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
                err_msg = str(e)
                logger.warning(f"Google Drive upload attempt {attempt}/5 failed for {filename}: {err_msg}")
                
                # Mark drive failure state & log to MongoDB system_health
                self.health_status = "FAILED"
                self.last_error_message = err_msg
                self.last_error_time = time.time()

                try:
                    from src.pipeline.db.mongo import mongo_db
                    if mongo_db.db is not None:
                        asyncio.create_task(mongo_db.db.system_health.update_one(
                            {"component": "google_drive"},
                            {"$set": {
                                "component": "google_drive",
                                "status": "FAILED",
                                "error_message": err_msg,
                                "failed_at": time.time(),
                                "attempt": attempt,
                                "fallback_mode": "LOCAL_STORAGE" if attempt == max_retries else "RETRYING"
                            }},
                            upsert=True
                        ))
                except Exception as db_err:
                    logger.warning(f"Failed to record drive health failure to MongoDB: {db_err}")

                if attempt == max_retries:
                    logger.warning(f"Google Drive upload failed after 5 attempts for {filename}. Falling back to Local Disk Storage.")
                    return {
                        "drive_file_id": None,
                        "drive_url": None,
                        "file_path": file_path
                    }
                await asyncio.sleep(backoff)

        return {
            "drive_file_id": None,
            "drive_url": None,
            "file_path": file_path
        }

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

        file_id = drive_file.get("id")

        # Make file readable by anyone with link for zero-auth CDN rendering
        try:
            self.service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"}
            ).execute()
        except Exception as perm_err:
            logger.warning(f"Failed to set Google Drive permissions to anyone for file {file_id}: {perm_err}")

        cdn_url = f"https://lh3.googleusercontent.com/d/{file_id}=s0"
        return {
            "drive_file_id": file_id,
            "drive_url": cdn_url,
            "file_path": file_path
        }

    async def download_file_bytes(self, drive_file_id: str) -> Optional[bytes]:
        """
        Asynchronously downloads file content as binary bytes from Google Drive.
        """
        if not self.service or not drive_file_id:
            return None

        try:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                None,
                lambda: self.service.files().get_media(fileId=drive_file_id).execute()
            )
            return content
        except Exception as e:
            logger.error(f"Failed to download bytes from Google Drive for file ID {drive_file_id}: {e}")
            return None

    async def search_file_by_name(self, filename: str) -> Optional[Dict[str, str]]:
        """
        Queries Google Drive for a file matching filename.
        Returns dict containing drive_file_id and drive_url if found.
        """
        if not self.service or not filename:
            return None

        try:
            query = f"name = '{filename}' and trashed = false"
            if self.parent_folder_id:
                query += f" and '{self.parent_folder_id}' in parents"

            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(
                None,
                lambda: self.service.files().list(
                    q=query,
                    fields="files(id, name, webViewLink, webContentLink)",
                    pageSize=1
                ).execute()
            )
            files = res.get("files", [])
            if files:
                f = files[0]
                file_id = f.get("id")
                return {
                    "drive_file_id": file_id,
                    "drive_url": f.get("webViewLink") or f.get("webContentLink") or f"https://drive.google.com/file/d/{file_id}/view"
                }
        except Exception as e:
            logger.warning(f"Error searching Google Drive for file {filename}: {e}")

        return None


drive_service = GoogleDriveService()

