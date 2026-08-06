# -*- coding: utf-8 -*-
"""
MongoDB Database Manager Module
-------------------------------
Provides asynchronous database operations for image metadata, upload jobs,
and worker queue persistence using Motor / PyMongo.
"""

import logging
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from src.pipeline.config import settings

logger = logging.getLogger("pipeline.mongo")


class MongoManager:
    """
    Singleton Async MongoDB Client & Database Manager.
    Handles connection pooling, automatic index creation, and queries.
    """
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

    async def connect(self):
        """Initializes Async Motor Client and sets up collections & indexes."""
        try:
            logger.info(f"Connecting to MongoDB at {settings.DATABASE_URL} ...")
            self.client = AsyncIOMotorClient(
                settings.DATABASE_URL,
                maxPoolSize=50,
                minPoolSize=10,
                serverSelectionTimeoutMS=5000
            )
            self.db = self.client[settings.DATABASE_NAME]

            # Verify connection
            await self.client.admin.command('ping')
            logger.info(f"Successfully connected to MongoDB database: {settings.DATABASE_NAME}")

            await self._create_indexes()

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            # Fallback for offline or lazy initialization
            self.db = None

    async def _create_indexes(self):
        """Creates indexes for fast queries on SHA256, Job ID, Status, and Date."""
        if self.db is None:
            return

        # Indexes for studios collection
        await self.db.studios.create_index("studio_id", unique=True)
        await self.db.studios.create_index("studio_name")

        # Indexes for events collection
        await self.db.events.create_index("event_id", unique=True)
        await self.db.events.create_index([("studio_id", 1), ("created_at", -1)])
        await self.db.events.create_index([("studio_id", 1), ("search_status", 1)])
        await self.db.events.create_index([("studio_id", 1), ("event_status", 1)])

        # Indexes for image_metadata collection
        await self.db.image_metadata.create_index("image_id", unique=True)
        await self.db.image_metadata.create_index("sha256")
        await self.db.image_metadata.create_index("job_id")
        await self.db.image_metadata.create_index("status")
        await self.db.image_metadata.create_index("created_at")
        await self.db.image_metadata.create_index([("studio_id", 1), ("event_id", 1), ("created_at", -1)])
        await self.db.image_metadata.create_index([("studio_id", 1), ("status", 1)])

        # Indexes for upload_jobs collection
        await self.db.upload_jobs.create_index("job_id", unique=True)
        await self.db.upload_jobs.create_index("status")

        # Indexes for worker_tasks collection
        await self.db.worker_tasks.create_index("task_id", unique=True)
        await self.db.worker_tasks.create_index("status")
        await self.db.worker_tasks.create_index("priority")
        await self.db.worker_tasks.create_index("created_at")

        # Indexes for recognition_sessions collection
        await self.db.recognition_sessions.create_index("session_id", unique=True)
        await self.db.recognition_sessions.create_index("expires_at")
        await self.db.recognition_sessions.create_index("client_ip")

        # Indexes for audit_logs collection
        await self.db.audit_logs.create_index("event_type")
        await self.db.audit_logs.create_index("timestamp")

        # Indexes for blacklisted_tokens collection (automatic TTL purge on expiration)
        await self.db.blacklisted_tokens.create_index("token_signature", unique=True)
        await self.db.blacklisted_tokens.create_index("expires_at", expireAfterSeconds=0)

        logger.info("MongoDB database indexes successfully verified.")

    async def close(self):
        """Closes MongoDB Client connections gracefully."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed.")

    # Data Access Utilities
    async def get_image_by_sha256(self, sha256_hash: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        return await self.db.image_metadata.find_one({"sha256": sha256_hash})

    async def insert_image_metadata(self, metadata: Dict[str, Any]):
        if self.db is not None:
            await self.db.image_metadata.insert_one(metadata)

    async def update_image_metadata(self, image_id: str, update_dict: Dict[str, Any]):
        if self.db is not None:
            await self.db.image_metadata.update_one(
                {"image_id": image_id},
                {"$set": update_dict}
            )

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        return await self.db.upload_jobs.find_one({"job_id": job_id})

    async def save_job(self, job_dict: Dict[str, Any]):
        if self.db is not None:
            await self.db.upload_jobs.replace_one(
                {"job_id": job_dict["job_id"]},
                job_dict,
                upsert=True
            )

    async def save_recognition_session(self, session_data: Dict[str, Any]):
        if self.db is not None:
            await self.db.recognition_sessions.replace_one(
                {"session_id": session_data["session_id"]},
                session_data,
                upsert=True
            )

    async def get_recognition_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        return await self.db.recognition_sessions.find_one({"session_id": session_id})

    async def log_recognition_event(self, recognition_record: Dict[str, Any]):
        if self.db is not None:
            await self.db.recognition_history.insert_one(recognition_record)


mongo_db = MongoManager()

