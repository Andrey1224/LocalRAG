"""Search services for BM25 and hybrid search functionality."""

import asyncio
import time
from typing import List, Dict, Any, Optional
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError

from app.core.config import settings, app_config
from app.core.logging import ServiceLogger


class ElasticsearchService:
    """Service for BM25 full-text search using Elasticsearch."""
    
    def __init__(self):
        self.logger = ServiceLogger("elasticsearch_service")
        self.client = AsyncElasticsearch(
            [settings.elasticsearch_url],
            timeout=30,
            retry_on_timeout=True
        )
        self.index_name = settings.elasticsearch_index
        
        search_config = app_config.search.get("bm25", {})
        self.top_k = search_config.get("top_k", 20)
        self.min_score = search_config.get("min_score", 0.1)
    
    async def ensure_index_exists(self):
        """Ensure the Elasticsearch index exists with proper mapping."""
        start_time = time.time()
        
        try:
            # Check if index exists
            exists = await self.client.indices.exists(index=self.index_name)
            
            if not exists:
                # Create index with mapping
                mapping = {
                    "mappings": {
                        "properties": {
                            "chunk_id": {"type": "keyword"},
                            "doc_id": {"type": "keyword"},
                            "text": {
                                "type": "text",
                                "analyzer": "standard",
                                "search_analyzer": "standard"
                            },
                            "doc_title": {
                                "type": "text",
                                "analyzer": "standard",
                                "fields": {
                                    "keyword": {"type": "keyword"}
                                }
                            },
                            "source": {"type": "keyword"},
                            "file_type": {"type": "keyword"},
                            "language": {"type": "keyword"},
                            "page": {"type": "integer"},
                            "section": {"type": "text"},
                            "char_start": {"type": "integer"},
                            "char_end": {"type": "integer"},
                            "chunk_index": {"type": "integer"},
                            "token_count": {"type": "integer"},
                            "char_count": {"type": "integer"},
                            "created_at": {"type": "date"}
                        }
                    },
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "analysis": {
                            "analyzer": {
                                "standard": {
                                    "type": "standard",
                                    "stopwords": "_english_"
                                }
                            }
                        }
                    }
                }
                
                await self.client.indices.create(
                    index=self.index_name,
                    body=mapping
                )
                
                duration_ms = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "create_index",
                    duration_ms,
                    success=True,
                    index_name=self.index_name
                )
            else:
                duration_ms = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "check_index",
                    duration_ms,
                    success=True,
                    index_name=self.index_name,
                    status="exists"
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "ensure_index",
                duration_ms,
                success=False,
                error=str(e),
                index_name=self.index_name
            )
            raise
    
    async def index_chunks(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """Index chunks in Elasticsearch for BM25 search."""
        start_time = time.time()
        
        try:
            if not chunks:
                return []
            
            # Ensure index exists
            await self.ensure_index_exists()
            
            # Prepare documents for bulk indexing
            docs = []
            indexed_chunk_ids = []
            
            for chunk in chunks:
                doc = {
                    "_index": self.index_name,
                    "_id": chunk["chunk_id"],
                    "_source": {
                        "chunk_id": chunk["chunk_id"],
                        "doc_id": chunk["doc_id"],
                        "text": chunk["text"],
                        "char_start": chunk["char_start"],
                        "char_end": chunk["char_end"],
                        "chunk_index": chunk["chunk_index"],
                        "token_count": chunk["token_count"],
                        "char_count": chunk["char_count"],
                        **chunk["metadata"]
                    }
                }
                docs.append(doc)
                indexed_chunk_ids.append(chunk["chunk_id"])
            
            # Bulk index documents
            from elasticsearch.helpers import async_bulk
            await async_bulk(self.client, docs)
            
            # Refresh index to make documents searchable
            await self.client.indices.refresh(index=self.index_name)
            
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "index_chunks",
                duration_ms,
                success=True,
                chunk_count=len(chunks),
                index_name=self.index_name
            )
            
            return indexed_chunk_ids
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "index_chunks",
                duration_ms,
                success=False,
                error=str(e),
                chunk_count=len(chunks) if chunks else 0
            )
            raise
    
    async def delete_document_chunks(self, doc_id: str) -> int:
        """Delete all chunks for a document from Elasticsearch."""
        start_time = time.time()
        
        try:
            # Delete by query
            response = await self.client.delete_by_query(
                index=self.index_name,
                body={
                    "query": {
                        "term": {
                            "doc_id": doc_id
                        }
                    }
                }
            )
            
            deleted_count = response.get("deleted", 0)
            
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "delete_document_chunks",
                duration_ms,
                success=True,
                doc_id=doc_id,
                deleted_count=deleted_count
            )
            
            return deleted_count
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "delete_document_chunks",
                duration_ms,
                success=False,
                error=str(e),
                doc_id=doc_id
            )
            raise
    
    async def search_chunks(
        self, 
        query: str, 
        top_k: Optional[int] = None,
        doc_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search chunks using BM25 algorithm."""
        start_time = time.time()
        
        try:
            if top_k is None:
                top_k = self.top_k
            
            # Build search query
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["text^2", "doc_title^1.5", "section"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO",
                                    "operator": "or"
                                }
                            }
                        ]
                    }
                },
                "size": top_k,
                "min_score": self.min_score,
                "_source": [
                    "chunk_id", "doc_id", "text", "doc_title", "source", 
                    "page", "section", "file_type", "language"
                ]
            }
            
            # Add document filter if specified
            if doc_filter:
                search_body["query"]["bool"]["filter"] = [
                    {"term": {"doc_id": doc_filter}}
                ]
            
            # Perform search
            response = await self.client.search(
                index=self.index_name,
                body=search_body
            )
            
            # Format results
            results = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                results.append({
                    "chunk_id": source["chunk_id"],
                    "doc_id": source["doc_id"],
                    "text": source["text"],
                    "score": hit["_score"],
                    "metadata": {
                        "doc_title": source.get("doc_title"),
                        "source": source.get("source"),
                        "page": source.get("page"),
                        "section": source.get("section"),
                        "file_type": source.get("file_type"),
                        "language": source.get("language"),
                    }
                })
            
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "search_chunks",
                duration_ms,
                success=True,
                query_length=len(query),
                results_count=len(results),
                top_k=top_k
            )
            
            return results
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "search_chunks",
                duration_ms,
                success=False,
                error=str(e),
                query_length=len(query) if query else 0
            )
            raise
    
    async def close(self):
        """Close Elasticsearch client."""
        await self.client.close()


class HybridSearchService:
    """Service for hybrid search combining BM25 and dense vector search."""
    
    def __init__(self):
        self.logger = ServiceLogger("hybrid_search")
        
        # Import services
        from app.services.embeddings import QdrantService
        
        self.es_service = ElasticsearchService()
        self.vector_service = QdrantService()
        
        # Load hybrid search configuration
        hybrid_config = app_config.search.get("hybrid", {})
        self.bm25_weight = hybrid_config.get("weights", {}).get("bm25", 0.3)
        self.dense_weight = hybrid_config.get("weights", {}).get("dense", 0.7)
        self.final_top_k = hybrid_config.get("final_top_k", 10)
        
        # Individual search configs
        self.bm25_top_k = app_config.search.get("bm25", {}).get("top_k", 20)
        self.dense_top_k = app_config.search.get("dense", {}).get("top_k", 20)
    
    def normalize_scores(self, results: List[Dict[str, Any]], max_score: float = 1.0) -> List[Dict[str, Any]]:
        """Normalize scores to 0-1 range."""
        if not results:
            return results
        
        scores = [r["score"] for r in results]
        min_score = min(scores)
        score_range = max(scores) - min_score
        
        if score_range == 0:
            # All scores are the same
            for result in results:
                result["normalized_score"] = max_score
        else:
            for result in results:
                normalized = (result["score"] - min_score) / score_range
                result["normalized_score"] = normalized * max_score
        
        return results
    
    def combine_results(
        self, 
        bm25_results: List[Dict[str, Any]], 
        dense_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Combine and re-rank results from BM25 and dense search."""
        
        # Normalize scores for fair comparison
        bm25_normalized = self.normalize_scores(bm25_results.copy())
        dense_normalized = self.normalize_scores(dense_results.copy())
        
        # Create a mapping of chunk_id to combined results
        combined_scores = {}
        chunk_data = {}
        
        # Process BM25 results
        for result in bm25_normalized:
            chunk_id = result["chunk_id"]
            combined_scores[chunk_id] = result["normalized_score"] * self.bm25_weight
            chunk_data[chunk_id] = result
            chunk_data[chunk_id]["bm25_score"] = result["score"]
            chunk_data[chunk_id]["dense_score"] = 0.0
        
        # Process dense results
        for result in dense_normalized:
            chunk_id = result["chunk_id"]
            dense_contribution = result["normalized_score"] * self.dense_weight
            
            if chunk_id in combined_scores:
                combined_scores[chunk_id] += dense_contribution
                chunk_data[chunk_id]["dense_score"] = result["score"]
            else:
                combined_scores[chunk_id] = dense_contribution
                chunk_data[chunk_id] = result
                chunk_data[chunk_id]["bm25_score"] = 0.0
                chunk_data[chunk_id]["dense_score"] = result["score"]
        
        # Sort by combined score
        sorted_chunks = sorted(
            combined_scores.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        # Format final results
        final_results = []
        for chunk_id, combined_score in sorted_chunks[:self.final_top_k]:
            result = chunk_data[chunk_id].copy()
            result["score"] = combined_score
            result["hybrid_score"] = combined_score
            final_results.append(result)
        
        return final_results
    
    async def search(
        self, 
        query: str, 
        doc_filter: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        """Perform hybrid search combining BM25 and dense vector search."""
        start_time = time.time()
        
        try:
            # Perform searches in parallel
            bm25_task = self.es_service.search_chunks(
                query=query,
                top_k=self.bm25_top_k,
                doc_filter=doc_filter
            )
            
            dense_task = self.vector_service.search_similar_chunks(
                query_text=query,
                top_k=self.dense_top_k,
                doc_filter=doc_filter
            )
            
            bm25_start = time.time()
            bm25_results, dense_results = await asyncio.gather(bm25_task, dense_task)
            bm25_time = (time.time() - bm25_start) * 1000
            
            dense_start = time.time()
            # Dense search time is included in the gather above
            dense_time = bm25_time  # Approximate since they run in parallel
            
            # Combine results
            combine_start = time.time()
            combined_results = self.combine_results(bm25_results, dense_results)
            combine_time = (time.time() - combine_start) * 1000
            
            # Timing information
            timing_info = {
                "bm25_time_ms": bm25_time,
                "dense_time_ms": dense_time,
                "combine_time_ms": combine_time,
                "total_time_ms": (time.time() - start_time) * 1000
            }
            
            self.logger.log_operation(
                "hybrid_search",
                timing_info["total_time_ms"],
                success=True,
                query_length=len(query),
                bm25_results=len(bm25_results),
                dense_results=len(dense_results),
                final_results=len(combined_results)
            )
            
            return combined_results, timing_info
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "hybrid_search",
                duration_ms,
                success=False,
                error=str(e),
                query_length=len(query) if query else 0
            )
            raise


# Import for type hints
from typing import Tuple