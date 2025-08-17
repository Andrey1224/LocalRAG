"""LLM service for generating answers using Ollama."""

import asyncio
import json
import time
from typing import List, Dict, Any, Optional

import httpx

from app.core.config import settings, app_config
from app.core.logging import ServiceLogger


class OllamaService:
    """Service for generating responses using Ollama LLM."""
    
    def __init__(self):
        self.logger = ServiceLogger("ollama_service")
        
        # LLM configuration
        llm_config = app_config.models.get("llm", {})
        self.model_name = llm_config.get("name", settings.llm_model)
        self.temperature = llm_config.get("temperature", 0.1)
        self.max_tokens = llm_config.get("max_tokens", settings.max_tokens)
        self.top_p = llm_config.get("top_p", 0.9)
        
        # Generation configuration
        generation_config = app_config.generation
        self.max_context_length = generation_config.get("max_context_length", settings.context_window)
        self.citation_format = generation_config.get("citation_format", "[source: {source}, page {page}]")
        self.system_prompt = generation_config.get("system_prompt", "")
        
        self.base_url = settings.ollama_base_url
        self.timeout = 60.0  # 60 seconds timeout for generation
    
    async def check_model_availability(self) -> bool:
        """Check if the required model is available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                
                models = response.json()
                available_models = [model["name"] for model in models.get("models", [])]
                
                is_available = self.model_name in available_models
                
                self.logger.log_operation(
                    "check_model_availability",
                    0,
                    success=True,
                    model_name=self.model_name,
                    available=is_available,
                    total_models=len(available_models)
                )
                
                return is_available
                
        except Exception as e:
            self.logger.log_operation(
                "check_model_availability",
                0,
                success=False,
                error=str(e),
                model_name=self.model_name
            )
            return False
    
    async def pull_model(self) -> bool:
        """Pull the model if it's not available."""
        try:
            self.logger.info("Pulling model", model_name=self.model_name)
            
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minutes for model pull
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": self.model_name}
                )
                response.raise_for_status()
                
                self.logger.log_operation(
                    "pull_model",
                    0,
                    success=True,
                    model_name=self.model_name
                )
                
                return True
                
        except Exception as e:
            self.logger.log_operation(
                "pull_model",
                0,
                success=False,
                error=str(e),
                model_name=self.model_name
            )
            return False
    
    def format_context(self, search_results: List[Dict[str, Any]]) -> str:
        """Format search results into context for the LLM."""
        if not search_results:
            return ""
        
        context_parts = []
        total_length = 0
        
        for i, result in enumerate(search_results):
            # Format citation info
            metadata = result.get("metadata", {})
            doc_title = metadata.get("doc_title", "Unknown Document")
            source = metadata.get("source", "unknown")
            page = metadata.get("page")
            section = metadata.get("section")
            
            # Create citation reference
            citation_info = f"[Document: {doc_title}"
            if page:
                citation_info += f", Page {page}"
            if section:
                citation_info += f", Section: {section}"
            citation_info += f", Source: {source}]"
            
            # Format the context chunk
            chunk_text = result["text"].strip()
            context_chunk = f"{citation_info}\n{chunk_text}\n"
            
            # Check if adding this chunk would exceed context limit
            if total_length + len(context_chunk) > self.max_context_length:
                break
            
            context_parts.append(context_chunk)
            total_length += len(context_chunk)
        
        return "\n".join(context_parts)
    
    def create_prompt(self, question: str, context: str) -> str:
        """Create the full prompt for the LLM."""
        prompt = f"""Контекст из документов:
{context}

Вопрос пользователя: {question}

Инструкции:
- Отвечай только на основе предоставленного контекста
- Обязательно включай цитаты в формате [source: название_документа, page номер_страницы]
- Если информации недостаточно, честно скажи "Недостаточно данных для точного ответа"
- Отвечай кратко и точно
- Используй только ту информацию, которая есть в контексте

Ответ:"""
        
        return prompt
    
    async def generate_response(
        self, 
        question: str, 
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate response using Ollama LLM."""
        start_time = time.time()
        
        try:
            # Check if model is available
            if not await self.check_model_availability():
                # Try to pull the model
                if not await self.pull_model():
                    raise ValueError(f"Model {self.model_name} is not available and could not be pulled")
            
            # Format context from search results
            context = self.format_context(search_results)
            
            if not context:
                return {
                    "answer": "Недостаточно данных для точного ответа.",
                    "citations": [],
                    "context_used": "",
                    "generation_info": {
                        "model": self.model_name,
                        "context_length": 0,
                        "search_results_used": 0
                    }
                }
            
            # Create prompt
            prompt = self.create_prompt(question, context)
            
            # Prepare request payload
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "system": self.system_prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "num_predict": self.max_tokens,
                }
            }
            
            # Generate response
            generation_start = time.time()
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()
                generated_text = result.get("response", "").strip()
                
                generation_time = (time.time() - generation_start) * 1000
            
            # Extract citations from search results
            citations = []
            for result in search_results:
                metadata = result.get("metadata", {})
                citation = {
                    "source": metadata.get("source", "unknown"),
                    "doc_title": metadata.get("doc_title", "Unknown Document"),
                    "section": metadata.get("section"),
                    "page": metadata.get("page"),
                    "chunk_id": result.get("chunk_id"),
                    "confidence": result.get("score", 0.0)
                }
                citations.append(citation)
            
            # Remove duplicates based on source and page
            unique_citations = []
            seen = set()
            for citation in citations:
                key = (citation["source"], citation.get("page"))
                if key not in seen:
                    unique_citations.append(citation)
                    seen.add(key)
            
            total_duration = (time.time() - start_time) * 1000
            
            self.logger.log_operation(
                "generate_response",
                total_duration,
                success=True,
                model=self.model_name,
                question_length=len(question),
                context_length=len(context),
                response_length=len(generated_text),
                generation_time_ms=generation_time,
                citations_count=len(unique_citations)
            )
            
            return {
                "answer": generated_text,
                "citations": unique_citations,
                "context_used": context,
                "generation_info": {
                    "model": self.model_name,
                    "context_length": len(context),
                    "search_results_used": len(search_results),
                    "generation_time_ms": generation_time,
                    "total_time_ms": total_duration
                }
            }
            
        except Exception as e:
            total_duration = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "generate_response",
                total_duration,
                success=False,
                error=str(e),
                model=self.model_name,
                question_length=len(question) if question else 0
            )
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Ollama service."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Check if service is running
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                
                models = response.json()
                available_models = [model["name"] for model in models.get("models", [])]
                
                return {
                    "status": "healthy",
                    "base_url": self.base_url,
                    "configured_model": self.model_name,
                    "model_available": self.model_name in available_models,
                    "total_models": len(available_models),
                    "available_models": available_models[:5]  # Show first 5 models
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "base_url": self.base_url,
                "configured_model": self.model_name,
                "error": str(e)
            }