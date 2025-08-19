"""Embedding service for vector operations."""

import time
from typing import Any, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sentence_transformers import SentenceTransformer

from app.core.config import app_config, settings
from app.core.logging import ServiceLogger


class EmbeddingService:
    """Service for generating embeddings using BGE model."""

    def __init__(self):
        self.logger = ServiceLogger("embedding_service")
        embedding_config = app_config.models.get("embedding", {})

        self.model_name = embedding_config.get("name", "BAAI/bge-small-en-v1.5")
        self.batch_size = embedding_config.get("batch_size", 32)
        self.max_length = embedding_config.get("max_length", 512)

        self.model = None
        self._model_loaded = False

    def _load_model(self):
        """Lazy load the embedding model."""
        if not self._model_loaded:
            start_time = time.time()
            try:
                self.model = SentenceTransformer(self.model_name)
                self._model_loaded = True

                load_time = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "load_embedding_model", load_time, success=True, model_name=self.model_name
                )
            except Exception as e:
                load_time = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "load_embedding_model",
                    load_time,
                    success=False,
                    error=str(e),
                    model_name=self.model_name,
                )
                raise

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        """Encode texts to embeddings."""
        self._load_model()

        start_time = time.time()
        try:
            # Truncate texts to max_length if needed
            truncated_texts = []
            for text in texts:
                if len(text) > self.max_length * 4:  # Rough estimation (4 chars per token)
                    truncated_texts.append(text[: self.max_length * 4])
                else:
                    truncated_texts.append(text)

            embeddings = self.model.encode(
                truncated_texts,
                batch_size=self.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
            )

            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "encode_texts",
                duration_ms,
                success=True,
                text_count=len(texts),
                embedding_dim=embeddings.shape[1] if len(embeddings.shape) > 1 else 0,
            )

            return embeddings

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "encode_texts", duration_ms, success=False, error=str(e), text_count=len(texts)
            )
            raise

    def encode_single_text(self, text: str) -> np.ndarray:
        """Encode single text to embedding."""
        embeddings = self.encode_texts([text])
        return embeddings[0] if len(embeddings) > 0 else np.array([])


class QdrantService:
    """Service for Qdrant vector database operations."""

    def __init__(self):
        self.logger = ServiceLogger("qdrant_service")
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=30)
        self.collection_name = settings.qdrant_collection_name
        self.embedding_service = EmbeddingService()

    async def ensure_collection_exists(self, vector_size: int = 384):
        """Ensure the collection exists with proper configuration."""
        start_time = time.time()

        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.collection_name not in collection_names:
                # Create collection
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )

                duration_ms = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "create_collection",
                    duration_ms,
                    success=True,
                    collection_name=self.collection_name,
                    vector_size=vector_size,
                )
            else:
                duration_ms = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "check_collection",
                    duration_ms,
                    success=True,
                    collection_name=self.collection_name,
                    status="exists",
                )

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "ensure_collection",
                duration_ms,
                success=False,
                error=str(e),
                collection_name=self.collection_name,
            )
            raise

    async def index_chunks(self, chunks: list[dict[str, Any]]) -> list[str]:
        """Index chunks in Qdrant with embeddings."""
        start_time = time.time()

        try:
            if not chunks:
                return []

            # Extract texts for embedding
            texts = [chunk["text"] for chunk in chunks]

            # Generate embeddings
            embeddings = self.embedding_service.encode_texts(texts)

            # Ensure collection exists
            await self.ensure_collection_exists(vector_size=embeddings.shape[1])

            # Prepare points for insertion
            points = []
            indexed_chunk_ids = []

            for i, chunk in enumerate(chunks):
                point_id = chunk["chunk_id"]
                embedding = embeddings[i].tolist()

                payload = {
                    "chunk_id": chunk["chunk_id"],
                    "doc_id": chunk["doc_id"],
                    "text": chunk["text"],
                    "char_start": chunk["char_start"],
                    "char_end": chunk["char_end"],
                    "chunk_index": chunk["chunk_index"],
                    "token_count": chunk["token_count"],
                    "char_count": chunk["char_count"],
                    **chunk["metadata"],
                }

                points.append(PointStruct(id=point_id, vector=embedding, payload=payload))
                indexed_chunk_ids.append(point_id)

            # Batch insert points
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                self.client.upsert(collection_name=self.collection_name, points=batch)

            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "index_chunks",
                duration_ms,
                success=True,
                chunk_count=len(chunks),
                collection_name=self.collection_name,
            )

            return indexed_chunk_ids

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "index_chunks",
                duration_ms,
                success=False,
                error=str(e),
                chunk_count=len(chunks) if chunks else 0,
            )
            raise

    async def delete_document_chunks(self, doc_id: str) -> int:
        """Delete all chunks for a document."""
        start_time = time.time()

        try:
            # Search for existing chunks with this doc_id
            search_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=10000,  # Assuming max chunks per document
            )

            existing_chunks = search_result[0]
            chunk_ids = [point.id for point in existing_chunks]

            if chunk_ids:
                # Delete existing chunks
                self.client.delete(collection_name=self.collection_name, points_selector=chunk_ids)

            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "delete_document_chunks",
                duration_ms,
                success=True,
                doc_id=doc_id,
                deleted_count=len(chunk_ids),
            )

            return len(chunk_ids)

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "delete_document_chunks", duration_ms, success=False, error=str(e), doc_id=doc_id
            )
            raise

    async def search_similar_chunks(
        self, query_text: str, top_k: int = 10, doc_filter: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Search for similar chunks."""
        start_time = time.time()

        try:
            # Generate query embedding
            query_embedding = self.embedding_service.encode_single_text(query_text)

            # Prepare filter if needed
            search_filter = None
            if doc_filter:
                search_filter = Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_filter))]
                )

            # Search
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding.tolist(),
                query_filter=search_filter,
                limit=top_k,
                with_payload=True,
                score_threshold=0.3,  # Minimum similarity threshold
            )

            # Format results
            results = []
            for result in search_results:
                results.append(
                    {
                        "chunk_id": result.payload["chunk_id"],
                        "doc_id": result.payload["doc_id"],
                        "text": result.payload["text"],
                        "score": result.score,
                        "metadata": {
                            "doc_title": result.payload.get("doc_title"),
                            "source": result.payload.get("source"),
                            "page": result.payload.get("page"),
                            "file_type": result.payload.get("file_type"),
                            "language": result.payload.get("language"),
                        },
                    }
                )

            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "search_similar_chunks",
                duration_ms,
                success=True,
                query_length=len(query_text),
                results_count=len(results),
                top_k=top_k,
            )

            return results

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "search_similar_chunks",
                duration_ms,
                success=False,
                error=str(e),
                query_length=len(query_text) if query_text else 0,
            )
            raise
