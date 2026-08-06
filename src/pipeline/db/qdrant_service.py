# -*- coding: utf-8 -*-
"""
Qdrant Vector Database Manager
------------------------------
Manages gRPC connection to Qdrant vector database, collection creation (faces_embed),
and batch upserting of 512-dimensional face feature vectors.
"""

import logging
from typing import List, Dict, Any, Optional
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as rest_models
from src.pipeline.config import settings

logger = logging.getLogger("pipeline.qdrant")


class QdrantService:
    """
    Qdrant gRPC Vector Database Service for 512-d Face Embeddings.
    """
    def __init__(self):
        self.client: Optional[AsyncQdrantClient] = None
        self.collection_name = settings.QDRANT_COLLECTION

    async def connect(self):
        """Connects to Qdrant host via gRPC/REST and ensures faces_embed collection exists."""
        try:
            logger.info(f"Connecting to Qdrant Vector DB at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}...")
            
            # Try gRPC client first on settings.QDRANT_PORT (6334)
            try:
                self.client = AsyncQdrantClient(
                    host=settings.QDRANT_HOST,
                    grpc_port=settings.QDRANT_PORT,
                    prefer_grpc=True,
                    timeout=10.0
                )
                collections_res = await self.client.get_collections()
            except Exception as grpc_err:
                logger.info(f"gRPC connection failed ({grpc_err}), falling back to HTTP REST port 6333...")
                self.client = AsyncQdrantClient(
                    host=settings.QDRANT_HOST,
                    port=6333,
                    prefer_grpc=False,
                    timeout=10.0
                )
                collections_res = await self.client.get_collections()

            collection_names = [col.name for col in collections_res.collections]

            if self.collection_name not in collection_names:
                logger.info(f"Creating Qdrant collection: {self.collection_name} (512 dimensions, Cosine metric)")
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=rest_models.VectorParams(
                        size=settings.EMBEDDING_DIMENSION,  # 512
                        distance=rest_models.Distance.COSINE
                    )
                )
            else:
                logger.info(f"Qdrant collection '{self.collection_name}' is active.")

        except Exception as e:
            logger.warning(f"Could not initialize Qdrant vector database client: {e}. Vector search will operate in fallback mode.")
            self.client = None


    async def upsert_face_embedding(
        self,
        vector_id: str,
        embedding_vector: List[float],
        payload: Dict[str, Any]
    ) -> bool:
        """Upserts a single 512-d L2 normalized face embedding into Qdrant."""
        if self.client is None:
            logger.warning("Qdrant client not initialized. Skipping vector upsert.")
            return False

        try:
            point = rest_models.PointStruct(
                id=vector_id,
                vector=embedding_vector,
                payload=payload
            )
            await self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upsert vector {vector_id} to Qdrant: {e}")
            return False

    async def batch_upsert_embeddings(
        self,
        points: List[Dict[str, Any]]
    ) -> bool:
        """Batch upserts multiple points to Qdrant for maximum throughput."""
        if self.client is None or not points:
            return False

        try:
            qdrant_points = [
                rest_models.PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p["payload"]
                ) for p in points
            ]
            await self.client.upsert(
                collection_name=self.collection_name,
                points=qdrant_points
            )
            return True
        except Exception as e:
            logger.error(f"Failed batch vector upsert: {e}")
    async def set_payload(
        self,
        point_id: str,
        payload: Dict[str, Any]
    ) -> bool:
        """Updates payload metadata for a vector point in Qdrant."""
        if self.client is None:
            return False
        try:
            await self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[point_id]
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to update payload for point {point_id}: {e}")
            return False

    async def search_nearest_neighbors(
        self,
        query_vector: List[float],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
        query_filter: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes nearest-neighbor cosine similarity search in Qdrant for a 512-d query vector.
        Supports query_filter for multi-tenant studio payload filtering (<2ms index execution).
        """
        if self.client is None or not query_vector:
            logger.warning("Qdrant client unavailable. Returning empty nearest neighbors result.")
            return []

        try:
            hits = []

            # 1. Try query_points (Modern qdrant-client 1.10+)
            if hasattr(self.client, "query_points"):
                query_res = await self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    score_threshold=score_threshold,
                    with_payload=True
                )
                hits = getattr(query_res, "points", [])
            # 2. Try search_points
            elif hasattr(self.client, "search_points"):
                res = await self.client.search_points(
                    collection_name=self.collection_name,
                    vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    score_threshold=score_threshold,
                    with_payload=True
                )
                hits = getattr(res, "result", res)
            # 3. Try search
            elif hasattr(self.client, "search"):
                hits = await self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=top_k,
                    score_threshold=score_threshold,
                    with_payload=True
                )

            results = []
            for hit in hits:
                results.append({
                    "id": str(getattr(hit, "id", "")),
                    "score": round(float(getattr(hit, "score", 0.0)), 4),
                    "payload": getattr(hit, "payload", {}) or {}
                })
            return results

        except Exception as e:
            logger.error(f"Qdrant vector search failed: {e}")
            return []



qdrant_service = QdrantService()

