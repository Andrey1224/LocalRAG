"""Question answering API endpoints."""

import asyncio
import time
from typing import Dict, Any

from fastapi import APIRouter, HTTPException

from app.core.logging import get_logger, get_trace_id
from app.models.base import AskRequest, AskResponse, Citation
from app.services.search import HybridSearchService
from app.services.reranker import RerankerService
from app.services.llm import OllamaService

router = APIRouter()
logger = get_logger(__name__)


class RAGPipeline:
    """Complete RAG pipeline combining search, reranking, and generation."""
    
    def __init__(self):
        self.search_service = HybridSearchService()
        self.reranker_service = RerankerService()
        self.llm_service = OllamaService()
        self.logger = get_logger("rag_pipeline")
    
    async def process_question(self, question: str) -> Dict[str, Any]:
        """Process a question through the complete RAG pipeline."""
        start_time = time.time()
        trace_id = get_trace_id()
        
        try:
            # Step 1: Hybrid search (BM25 + Dense)
            search_start = time.time()
            search_results, search_timing = await self.search_service.search(question)
            search_time = (time.time() - search_start) * 1000
            
            if not search_results:
                return {
                    "answer": "Не найдено релевантных документов для ответа на ваш вопрос.",
                    "citations": [],
                    "debug": {
                        "trace_id": trace_id,
                        "search_results_count": 0,
                        "reranked_results_count": 0,
                        "search_time_ms": search_time,
                        "rerank_time_ms": 0,
                        "generation_time_ms": 0,
                        "total_time_ms": (time.time() - start_time) * 1000,
                        "confidence_score": 0.0
                    }
                }
            
            # Step 2: Reranking
            rerank_start = time.time()
            reranked_results = self.reranker_service.rerank_results(question, search_results)
            rerank_time = (time.time() - rerank_start) * 1000
            
            # Step 3: LLM Generation
            generation_start = time.time()
            llm_response = await self.llm_service.generate_response(question, reranked_results)
            generation_time = (time.time() - generation_start) * 1000
            
            # Calculate confidence score based on search scores
            avg_score = sum(r.get("score", 0) for r in reranked_results) / len(reranked_results) if reranked_results else 0
            confidence_score = min(avg_score, 1.0)  # Cap at 1.0
            
            # Format citations
            citations = []
            for citation_data in llm_response.get("citations", []):
                citation = Citation(
                    source=citation_data.get("source", "unknown"),
                    doc_title=citation_data.get("doc_title", "Unknown Document"),
                    section=citation_data.get("section"),
                    page=citation_data.get("page"),
                    chunk_id=citation_data.get("chunk_id"),
                    confidence=citation_data.get("confidence")
                )
                citations.append(citation)
            
            total_time = (time.time() - start_time) * 1000
            
            # Debug information
            debug_info = {
                "trace_id": trace_id,
                "search_results_count": len(search_results),
                "reranked_results_count": len(reranked_results),
                "bm25_time_ms": search_timing.get("bm25_time_ms", 0),
                "dense_time_ms": search_timing.get("dense_time_ms", 0),
                "search_combine_time_ms": search_timing.get("combine_time_ms", 0),
                "rerank_time_ms": rerank_time,
                "generation_time_ms": generation_time,
                "total_time_ms": total_time,
                "confidence_score": confidence_score,
                "model_used": llm_response.get("generation_info", {}).get("model"),
                "context_length": llm_response.get("generation_info", {}).get("context_length", 0)
            }
            
            self.logger.info(
                "RAG pipeline completed",
                trace_id=trace_id,
                question_length=len(question),
                total_time_ms=total_time,
                search_results=len(search_results),
                reranked_results=len(reranked_results),
                citations_count=len(citations),
                confidence_score=confidence_score
            )
            
            return {
                "answer": llm_response.get("answer", ""),
                "citations": citations,
                "debug": debug_info
            }
            
        except Exception as e:
            total_time = (time.time() - start_time) * 1000
            self.logger.error(
                "RAG pipeline failed",
                trace_id=trace_id,
                error=str(e),
                question_length=len(question) if question else 0,
                total_time_ms=total_time
            )
            raise


rag_pipeline = RAGPipeline()


@router.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """
    Ask a question and get an answer based on indexed documents.
    
    - **question**: The question to ask (5-500 characters)
    
    Returns an answer with citations and debug information.
    """
    start_time = time.time()
    
    try:
        logger.info(
            "Processing question",
            question_length=len(request.question),
            trace_id=get_trace_id()
        )
        
        # Validate question
        question = request.question.strip()
        if len(question) < 5:
            raise HTTPException(
                status_code=400,
                detail="Question is too short (minimum 5 characters)"
            )
        
        if len(question) > 500:
            raise HTTPException(
                status_code=400,
                detail="Question is too long (maximum 500 characters)"
            )
        
        # Process through RAG pipeline
        result = await rag_pipeline.process_question(question)
        
        total_duration = (time.time() - start_time) * 1000
        
        logger.info(
            "Question processing completed",
            trace_id=get_trace_id(),
            total_duration_ms=total_duration,
            answer_length=len(result.get("answer", "")),
            citations_count=len(result.get("citations", []))
        )
        
        return AskResponse(
            answer=result["answer"],
            citations=result["citations"],
            debug=result.get("debug"),
            message=f"Answer generated in {total_duration:.1f}ms"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Question processing failed",
            error=str(e),
            trace_id=get_trace_id()
        )
        
        # Classify error types
        error_msg = str(e).lower()
        if "timeout" in error_msg:
            raise HTTPException(
                status_code=504,
                detail="Request timeout - please try again"
            )
        elif "model" in error_msg and ("not available" in error_msg or "not found" in error_msg):
            raise HTTPException(
                status_code=503,
                detail="LLM service temporarily unavailable"
            )
        elif "connection" in error_msg or "network" in error_msg:
            raise HTTPException(
                status_code=503,
                detail="External service connection failed"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Internal processing error"
            )


@router.get("/ask/health")
async def ask_health_check():
    """Health check for all RAG pipeline components."""
    try:
        # Check all services
        health_checks = {}
        
        # Check Ollama LLM
        try:
            llm_health = await rag_pipeline.llm_service.health_check()
            health_checks["llm"] = llm_health
        except Exception as e:
            health_checks["llm"] = {"status": "unhealthy", "error": str(e)}
        
        # Check search services (basic connectivity)
        try:
            # Test Elasticsearch
            es_client = rag_pipeline.search_service.es_service.client
            await es_client.cluster.health(timeout="5s")
            health_checks["elasticsearch"] = {"status": "healthy"}
        except Exception as e:
            health_checks["elasticsearch"] = {"status": "unhealthy", "error": str(e)}
        
        try:
            # Test Qdrant
            qdrant_client = rag_pipeline.search_service.vector_service.client
            collections = qdrant_client.get_collections()
            health_checks["qdrant"] = {
                "status": "healthy",
                "collections_count": len(collections.collections)
            }
        except Exception as e:
            health_checks["qdrant"] = {"status": "unhealthy", "error": str(e)}
        
        # Overall status
        all_healthy = all(
            check.get("status") == "healthy" 
            for check in health_checks.values()
        )
        
        overall_status = "healthy" if all_healthy else "degraded"
        
        return {
            "status": overall_status,
            "components": health_checks,
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time()
        }