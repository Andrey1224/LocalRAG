"""Reranking service using BGE reranker model."""

import time
from typing import Any

import torch
from FlagEmbedding import FlagReranker

from app.core.config import app_config
from app.core.logging import ServiceLogger


class RerankerService:
    """Service for reranking search results using BGE reranker."""

    def __init__(self):
        self.logger = ServiceLogger("reranker_service")
        reranker_config = app_config.models.get("reranker", {})

        self.model_name = reranker_config.get("name", "BAAI/bge-reranker-v2-m3")
        self.batch_size = reranker_config.get("batch_size", 16)
        self.max_length = reranker_config.get("max_length", 512)
        self.top_k = reranker_config.get("top_k", 5)

        self.model = None
        self._model_loaded = False

    def _load_model(self):
        """Lazy load the reranker model."""
        if not self._model_loaded:
            start_time = time.time()
            try:
                self.model = FlagReranker(
                    self.model_name,
                    use_fp16=torch.cuda.is_available(),  # Use FP16 if CUDA available
                )
                self._model_loaded = True

                load_time = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "load_reranker_model", load_time, success=True, model_name=self.model_name
                )
            except Exception as e:
                load_time = (time.time() - start_time) * 1000
                self.logger.log_operation(
                    "load_reranker_model",
                    load_time,
                    success=False,
                    error=str(e),
                    model_name=self.model_name,
                )
                raise

    def rerank_results(
        self, query: str, search_results: list[dict[str, Any]], top_k: int = None
    ) -> list[dict[str, Any]]:
        """Rerank search results using the reranker model."""
        if not search_results:
            return []

        if top_k is None:
            top_k = self.top_k

        start_time = time.time()

        try:
            self._load_model()

            # Prepare query-document pairs
            pairs = []
            for result in search_results:
                # Truncate text if too long
                text = result["text"]
                if len(text) > self.max_length * 4:  # Rough char to token ratio
                    text = text[: self.max_length * 4]

                pairs.append([query, text])

            # Compute reranking scores
            scores = self.model.compute_score(pairs, batch_size=self.batch_size)

            # Handle both single score and batch scores
            if isinstance(scores, (int, float)):
                scores = [scores]

            # Add reranking scores to results
            reranked_results = []
            for i, result in enumerate(search_results):
                reranked_result = result.copy()
                reranked_result["rerank_score"] = float(scores[i])
                reranked_result["original_score"] = result["score"]
                reranked_result["score"] = float(scores[i])  # Use rerank score as primary
                reranked_results.append(reranked_result)

            # Sort by reranking score
            reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)

            # Return top_k results
            final_results = reranked_results[:top_k]

            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "rerank_results",
                duration_ms,
                success=True,
                input_count=len(search_results),
                output_count=len(final_results),
                top_k=top_k,
            )

            return final_results

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "rerank_results",
                duration_ms,
                success=False,
                error=str(e),
                input_count=len(search_results) if search_results else 0,
            )
            raise
