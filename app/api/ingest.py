"""Document ingestion API endpoints."""

import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.models.base import IngestRequest, IngestResponse
from app.services.chunking import TextChunker
from app.services.document_parser import UniversalDocumentParser
from app.services.embeddings import QdrantService
from app.services.search import ElasticsearchService

router = APIRouter()
logger = get_logger(__name__)

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class IngestService:
    """Service for document ingestion pipeline."""

    def __init__(self):
        self.parser = UniversalDocumentParser()
        self.chunker = TextChunker()
        self.vector_service = QdrantService()
        self.search_service = ElasticsearchService()
        self.logger = get_logger("ingest_service")

    async def check_document_exists(self, content_hash: str, db) -> dict[str, Any]:
        """Check if document with same content hash already exists."""
        try:
            result = db.execute(
                text(
                    "SELECT doc_id, title, total_chunks FROM documents WHERE content_hash = :hash"
                ),
                {"hash": content_hash},
            ).fetchone()

            if result:
                return {
                    "exists": True,
                    "doc_id": result[0],
                    "title": result[1],
                    "total_chunks": result[2],
                }
            return {"exists": False}

        except Exception as e:
            self.logger.error("Database check failed", error=str(e))
            return {"exists": False}

    async def save_document_metadata(self, doc_data: dict[str, Any], chunks_count: int, db) -> str:
        """Save document metadata to database."""
        try:
            doc_id = str(uuid.uuid4())

            db.execute(
                text(
                    """
                    INSERT INTO documents
                    (id, doc_id, title, source_path, content_hash, file_type, language,
                     total_chunks, file_size_bytes, created_at, updated_at)
                    VALUES
                    (:id, :doc_id, :title, :source_path, :content_hash, :file_type, :language,
                     :total_chunks, :file_size_bytes, NOW(), NOW())
                """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "doc_id": doc_id,
                    "title": doc_data["metadata"].get("title", "Untitled"),
                    "source_path": doc_data["source_path"],
                    "content_hash": doc_data["content_hash"],
                    "file_type": doc_data["file_type"],
                    "language": doc_data["language"],
                    "total_chunks": chunks_count,
                    "file_size_bytes": doc_data["file_size_bytes"],
                },
            )
            db.commit()

            return doc_id

        except Exception as e:
            db.rollback()
            self.logger.error("Failed to save document metadata", error=str(e))
            raise

    async def process_single_document(self, file_path: str, db) -> dict[str, Any]:
        """Process a single document through the full pipeline."""
        start_time = time.time()

        try:
            # Parse document
            doc_data = await self.parser.parse_document(file_path)

            # Check if document already exists (idempotent operation)
            existing_doc = await self.check_document_exists(doc_data["content_hash"], db)
            if existing_doc["exists"]:
                self.logger.info(
                    "Document already exists, skipping",
                    file_path=file_path,
                    doc_id=existing_doc["doc_id"],
                )
                return {
                    "status": "skipped",
                    "reason": "already_exists",
                    "doc_id": existing_doc["doc_id"],
                    "chunks": existing_doc["total_chunks"],
                }

            # Create chunks
            doc_data["doc_id"] = str(uuid.uuid4())
            chunks = self.chunker.create_chunks(doc_data["text"], doc_data)

            if not chunks:
                return {
                    "status": "error",
                    "reason": "no_chunks_created",
                    "error": "Document produced no valid chunks",
                }

            # Check chunks limit
            max_chunks = self.chunker.max_chunks_per_doc
            if len(chunks) > max_chunks:
                return {
                    "status": "error",
                    "reason": "too_many_chunks",
                    "error": f"Document produced {len(chunks)} chunks, max allowed is {max_chunks}",
                }

            # Index chunks in both Qdrant and Elasticsearch
            vector_chunk_ids = await self.vector_service.index_chunks(chunks)
            search_chunk_ids = await self.search_service.index_chunks(chunks)

            # Save document metadata
            doc_id = await self.save_document_metadata(doc_data, len(chunks), db)

            duration_ms = (time.time() - start_time) * 1000
            self.logger.info(
                "Document processed successfully",
                file_path=file_path,
                doc_id=doc_id,
                chunks_count=len(chunks),
                duration_ms=duration_ms,
            )

            return {
                "status": "indexed",
                "doc_id": doc_id,
                "chunks": len(chunks),
                "chunk_ids": vector_chunk_ids,
            }

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            self.logger.error(
                "Document processing failed",
                file_path=file_path,
                error=error_msg,
                duration_ms=duration_ms,
            )

            # Classify error
            if "not found" in error_msg.lower():
                error_code = "FILE_NOT_FOUND"
            elif "protected" in error_msg.lower() or "encrypted" in error_msg.lower():
                error_code = "PDF_PROTECTED"
            elif "too large" in error_msg.lower():
                error_code = "FILE_TOO_LARGE"
            elif "unsupported" in error_msg.lower():
                error_code = "UNSUPPORTED_FORMAT"
            elif "parsing failed" in error_msg.lower():
                error_code = "PARSING_FAILED"
            elif "too_many_chunks" in error_msg:
                error_code = "CHUNK_LIMIT_EXCEEDED"
            else:
                error_code = "PROCESSING_ERROR"

            return {
                "status": "error",
                "error_code": error_code,
                "error": error_msg,
                "file_path": file_path,
            }

    async def delete_missing_documents(self, provided_paths: list[str], db) -> int:
        """Delete documents not in provided paths list."""
        try:
            # Get all existing documents
            result = db.execute(text("SELECT doc_id, source_path FROM documents")).fetchall()

            existing_docs = {row[1]: row[0] for row in result}  # path -> doc_id

            # Find documents to delete
            docs_to_delete = []
            for path, doc_id in existing_docs.items():
                if path not in provided_paths:
                    docs_to_delete.append((doc_id, path))

            # Delete from Qdrant and database
            deleted_count = 0
            for doc_id, path in docs_to_delete:
                try:
                    # Delete from both Qdrant and Elasticsearch
                    await self.vector_service.delete_document_chunks(doc_id)
                    await self.search_service.delete_document_chunks(doc_id)

                    # Delete from database
                    db.execute(
                        text("DELETE FROM documents WHERE doc_id = :doc_id"), {"doc_id": doc_id}
                    )
                    db.commit()

                    deleted_count += 1
                    self.logger.info("Deleted missing document", doc_id=doc_id, path=path)

                except Exception as e:
                    self.logger.error(
                        "Failed to delete document", doc_id=doc_id, path=path, error=str(e)
                    )
                    continue

            return deleted_count

        except Exception as e:
            self.logger.error("Failed to delete missing documents", error=str(e))
            return 0


ingest_service = IngestService()


@router.post("/ingest", response_model=IngestResponse)
async def ingest_documents(request: IngestRequest, db=Depends(get_db)):
    """
    Ingest documents for indexing and search.

    - **paths**: List of file paths or URLs to process
    - **delete_missing**: If true, delete documents not in paths list
    """
    start_time = time.time()

    try:
        logger.info(
            "Starting document ingestion",
            paths_count=len(request.paths),
            delete_missing=request.delete_missing,
        )

        # Validate paths
        if not request.paths:
            raise HTTPException(status_code=400, detail="No paths provided")

        # Check supported formats
        unsupported_paths = []
        for path in request.paths:
            if not ingest_service.parser.pdf_parser.is_supported_format(path):
                unsupported_paths.append(path)

        if unsupported_paths:
            raise HTTPException(
                status_code=415, detail=f"Unsupported file formats: {unsupported_paths}"
            )

        # Process documents
        results = []
        indexed_count = 0
        skipped_count = 0
        errors = []
        doc_ids = []

        for path in request.paths:
            try:
                result = await ingest_service.process_single_document(path, db)
                results.append(result)

                if result["status"] == "indexed":
                    indexed_count += 1
                    doc_ids.append(result["doc_id"])
                elif result["status"] == "skipped":
                    skipped_count += 1
                    doc_ids.append(result["doc_id"])
                else:  # error
                    errors.append(
                        {"path": path, "error": result["error"], "code": result["error_code"]}
                    )

            except Exception as e:
                errors.append({"path": path, "error": str(e), "code": "UNEXPECTED_ERROR"})

        # Delete missing documents if requested
        deleted_count = 0
        if request.delete_missing:
            deleted_count = await ingest_service.delete_missing_documents(request.paths, db)

        # Calculate total time
        total_duration = (time.time() - start_time) * 1000

        logger.info(
            "Document ingestion completed",
            indexed=indexed_count,
            skipped=skipped_count,
            errors=len(errors),
            deleted=deleted_count,
            duration_ms=total_duration,
        )

        return IngestResponse(
            indexed=indexed_count,
            skipped=skipped_count,
            errors=errors,
            doc_ids=doc_ids,
            message=f"Processed {len(request.paths)} documents in {total_duration:.1f}ms",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Ingestion failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/ingest/status")
async def get_ingestion_status(db=Depends(get_db)):
    """Get current ingestion status and statistics."""
    try:
        # Get document statistics
        stats = db.execute(
            text(
                """
                SELECT
                    COUNT(*) as total_documents,
                    SUM(total_chunks) as total_chunks,
                    SUM(file_size_bytes) as total_size_bytes,
                    COUNT(DISTINCT language) as languages_count
                FROM documents
            """
            )
        ).fetchone()

        # Get documents by type
        types_stats = db.execute(
            text(
                """
                SELECT file_type, COUNT(*) as count
                FROM documents
                GROUP BY file_type
                ORDER BY count DESC
            """
            )
        ).fetchall()

        # Get recent documents
        recent_docs = db.execute(
            text(
                """
                SELECT doc_id, title, source_path, total_chunks, created_at
                FROM documents
                ORDER BY created_at DESC
                LIMIT 10
            """
            )
        ).fetchall()

        return {
            "statistics": {
                "total_documents": stats[0] if stats else 0,
                "total_chunks": stats[1] if stats else 0,
                "total_size_bytes": stats[2] if stats else 0,
                "languages_count": stats[3] if stats else 0,
            },
            "file_types": [{"type": row[0], "count": row[1]} for row in types_stats],
            "recent_documents": [
                {
                    "doc_id": row[0],
                    "title": row[1],
                    "source_path": row[2],
                    "total_chunks": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                }
                for row in recent_docs
            ],
        }

    except Exception as e:
        logger.error("Failed to get ingestion status", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to retrieve status")
