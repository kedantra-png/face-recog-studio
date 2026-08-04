# -*- coding: utf-8 -*-
"""
Database & Vector Collection Cleanup Script
--------------------------------------------
Completely wipes and resets all MongoDB database collections, Qdrant vector collections,
and local temporary upload directories to guarantee a 100% clean slate.
"""

import os
import sys
import asyncio
import shutil
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from qdrant_client import AsyncQdrantClient

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("clean_databases")

MONGO_URL = "mongodb://localhost:27017"
DATABASES_TO_DROP = [
    "face_recog_db_v2",
    "face_recog_db_final",
    "face_recognition_db",
    "auraface_db"
]

QDRANT_HOST = "187.127.189.238"
QDRANT_GRPC_PORT = 6334
QDRANT_HTTP_PORT = 6333
QDRANT_COLLECTIONS_TO_DROP = [
    "faces_embed_v2",
    "faces_embed",
    "faces"

]


async def clean_mongodb():
    """Drops all MongoDB face recognition databases and collections."""
    logger.info("--- Cleaning MongoDB Databases ---")
    try:
        client = AsyncIOMotorClient(MONGO_URL, serverSelectionTimeoutMS=3000)
        existing_dbs = await client.list_database_names()
        logger.info(f"Existing MongoDB Databases: {existing_dbs}")

        for db_name in DATABASES_TO_DROP:
            if db_name in existing_dbs:
                await client.drop_database(db_name)
                logger.info(f"Successfully dropped MongoDB database: '{db_name}'")
            else:
                logger.info(f"MongoDB database '{db_name}' does not exist (Skipped)")

        # Create fresh face_recog_db_v2 with indexes
        db_v2 = client["face_recog_db_v2"]
        await db_v2.image_metadata.create_index("image_id", unique=True)
        await db_v2.image_metadata.create_index("created_at")
        await db_v2.security_audit_logs.create_index("timestamp")
        logger.info("Initialized fresh MongoDB database 'face_recog_db_v2' with clean indexes.")

    except Exception as e:
        logger.error(f"Error cleaning MongoDB: {e}")


async def clean_qdrant():
    """Deletes and re-creates Qdrant 512-d vector collections."""
    logger.info("--- Cleaning Qdrant Vector DB Collections ---")
    qdrant_client = None

    try:
        logger.info(f"Connecting to Qdrant gRPC on {QDRANT_HOST}:{QDRANT_GRPC_PORT}...")
        qdrant_client = AsyncQdrantClient(
            host=QDRANT_HOST,
            port=QDRANT_GRPC_PORT,
            prefer_grpc=True,
            timeout=5.0
        )
        collections_res = await qdrant_client.get_collections()
    except Exception as e:
        logger.info(f"gRPC connection attempt failed ({e}), falling back to HTTP REST port {QDRANT_HTTP_PORT}...")
        try:
            qdrant_client = AsyncQdrantClient(
                host=QDRANT_HOST,
                port=QDRANT_HTTP_PORT,
                prefer_grpc=False,
                timeout=5.0
            )
            collections_res = await qdrant_client.get_collections()
        except Exception as http_err:
            logger.error(f"Could not connect to Qdrant vector database: {http_err}")
            return

    try:
        existing_cols = [c.name for c in collections_res.collections]
        logger.info(f"Existing Qdrant Vector Collections: {existing_cols}")

        for col in QDRANT_COLLECTIONS_TO_DROP:
            if col in existing_cols:
                await qdrant_client.delete_collection(collection_name=col)
                logger.info(f"Successfully deleted Qdrant vector collection: '{col}'")
            else:
                logger.info(f"Qdrant collection '{col}' does not exist (Skipped)")

        # Create fresh faces_embed_v2 collection
        from qdrant_client.http import models as rest_models
        await qdrant_client.create_collection(
            collection_name="faces_embed_v2",
            vectors_config=rest_models.VectorParams(
                size=512,
                distance=rest_models.Distance.COSINE
            )
        )
        logger.info("Created fresh Qdrant vector collection 'faces_embed_v2' (512-d, Cosine distance).")

    except Exception as e:
        logger.error(f"Error cleaning Qdrant collections: {e}")


def clean_local_temp_files():
    """Removes temporary uploads and debug outputs from local disk."""
    logger.info("--- Cleaning Local Temporary Storage ---")
    dirs_to_clean = ["temp_uploads", "debug_output"]
    for dir_name in dirs_to_clean:
        dir_path = os.path.join(os.getcwd(), dir_name)
        if os.path.exists(dir_path):
            try:
                shutil.rmtree(dir_path)
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"Successfully wiped local directory: '{dir_name}'")
            except Exception as e:
                logger.warning(f"Could not wipe directory '{dir_name}': {e}")


async def main():
    logger.info("=== STARTING FULL PIPELINE DATABASE, VECTOR & DRIVE CLEANUP ===")
    await clean_mongodb()
    await clean_qdrant()
    await clean_google_drive()
    clean_local_temp_files()
    logger.info("=== CLEANUP COMPLETE: MongoDB, Qdrant & Google Drive are 100% reset! ===")


async def clean_google_drive():
    """Deletes all uploaded files inside the configured Google Drive parent folder."""
    logger.info("--- Cleaning Google Drive Storage ---")
    try:
        sys.path.insert(0, os.getcwd())
        from src.pipeline.storage.drive_service import drive_service

        if not drive_service.service:
            logger.info("Google Drive service not available (Skipped)")
            return

        parent_id = drive_service.parent_folder_id
        if not parent_id:
            logger.info("No parent folder ID set for Google Drive (Skipped)")
            return

        loop = asyncio.get_event_loop()
        query = f"'{parent_id}' in parents and trashed = false"
        res = await loop.run_in_executor(
            None,
            lambda: drive_service.service.files().list(
                q=query,
                fields="files(id, name)",
                pageSize=1000
            ).execute()
        )

        files = res.get("files", [])
        logger.info(f"Found {len(files)} file(s) in Google Drive folder '{parent_id}' to purge.")

        deleted_count = 0
        for f in files:
            file_id = f.get("id")
            fname = f.get("name")
            try:
                await loop.run_in_executor(
                    None,
                    lambda fid=file_id: drive_service.service.files().delete(fileId=fid).execute()
                )
                deleted_count += 1
                logger.info(f"Deleted Google Drive file: '{fname}' (ID: {file_id})")
            except Exception as del_err:
                logger.warning(f"Failed to delete Google Drive file '{fname}': {del_err}")

        logger.info(f"Successfully purged {deleted_count} file(s) from Google Drive.")

    except Exception as e:
        logger.error(f"Error cleaning Google Drive storage: {e}")


if __name__ == "__main__":
    asyncio.run(main())

