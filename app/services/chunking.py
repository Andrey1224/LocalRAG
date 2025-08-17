"""Text chunking service for document processing."""

import uuid
from typing import List, Dict, Any
import tiktoken
from datetime import datetime

from app.core.config import app_config
from app.core.logging import ServiceLogger


class TextChunker:
    """Service for splitting text into chunks with overlap."""
    
    def __init__(self):
        self.logger = ServiceLogger("text_chunker")
        chunking_config = app_config.chunking
        
        self.chunk_size = chunking_config.get("chunk_size", 1000)
        self.overlap = chunking_config.get("overlap", 100)
        self.min_chunk_size = chunking_config.get("min_chunk_size", 50)
        self.separators = chunking_config.get("separators", ["\n\n", "\n", ". ", "? ", "! ", " "])
        
        # Initialize tokenizer for accurate token counting
        self.tokenizer = tiktoken.get_encoding("cl100k_base")  # GPT-3.5/4 tokenizer
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def split_text_by_separators(self, text: str, separators: List[str]) -> List[str]:
        """Split text using hierarchical separators."""
        if not separators:
            return [text]
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        parts = text.split(separator)
        
        if len(parts) == 1:
            # Current separator didn't split the text, try next
            return self.split_text_by_separators(text, remaining_separators)
        
        result = []
        for part in parts:
            if self.count_tokens(part) > self.chunk_size:
                # Part is still too large, split further
                sub_parts = self.split_text_by_separators(part, remaining_separators)
                result.extend(sub_parts)
            else:
                result.append(part)
        
        return result
    
    def create_chunks_with_overlap(self, text_parts: List[str]) -> List[str]:
        """Create chunks with overlap from text parts."""
        chunks = []
        current_chunk = ""
        overlap_buffer = ""
        
        for part in text_parts:
            part = part.strip()
            if not part:
                continue
            
            # Try to add part to current chunk
            potential_chunk = current_chunk + (" " if current_chunk else "") + part
            
            if self.count_tokens(potential_chunk) <= self.chunk_size:
                current_chunk = potential_chunk
            else:
                # Current chunk is ready, save it
                if current_chunk and self.count_tokens(current_chunk) >= self.min_chunk_size:
                    chunks.append(current_chunk)
                    
                    # Prepare overlap for next chunk
                    overlap_tokens = self.count_tokens(current_chunk)
                    if overlap_tokens > self.overlap:
                        # Take last part of current chunk as overlap
                        overlap_text = current_chunk
                        while self.count_tokens(overlap_text) > self.overlap:
                            words = overlap_text.split()
                            if len(words) <= 1:
                                break
                            overlap_text = " ".join(words[1:])
                        overlap_buffer = overlap_text
                    else:
                        overlap_buffer = current_chunk
                
                # Start new chunk with overlap and current part
                current_chunk = overlap_buffer + (" " if overlap_buffer else "") + part
                
                # If even with overlap the part is too large, split it
                if self.count_tokens(current_chunk) > self.chunk_size:
                    # Force split the large part
                    words = part.split()
                    temp_chunk = overlap_buffer
                    
                    for word in words:
                        test_chunk = temp_chunk + (" " if temp_chunk else "") + word
                        if self.count_tokens(test_chunk) <= self.chunk_size:
                            temp_chunk = test_chunk
                        else:
                            if temp_chunk and self.count_tokens(temp_chunk) >= self.min_chunk_size:
                                chunks.append(temp_chunk)
                            temp_chunk = word
                    
                    current_chunk = temp_chunk
        
        # Add final chunk
        if current_chunk and self.count_tokens(current_chunk) >= self.min_chunk_size:
            chunks.append(current_chunk)
        
        return chunks
    
    def create_chunks(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create chunks from text with metadata."""
        start_time = time.time()
        
        try:
            # First, split text by separators
            text_parts = self.split_text_by_separators(text, self.separators)
            
            # Create chunks with overlap
            chunk_texts = self.create_chunks_with_overlap(text_parts)
            
            # Create chunk objects with metadata
            chunks = []
            char_position = 0
            
            for i, chunk_text in enumerate(chunk_texts):
                chunk_id = f"{metadata.get('doc_id', 'unknown')}_{i+1:03d}"
                
                chunk = {
                    "chunk_id": chunk_id,
                    "doc_id": metadata.get("doc_id"),
                    "text": chunk_text,
                    "char_start": char_position,
                    "char_end": char_position + len(chunk_text),
                    "chunk_index": i,
                    "token_count": self.count_tokens(chunk_text),
                    "char_count": len(chunk_text),
                    "metadata": {
                        "doc_title": metadata.get("title"),
                        "source": metadata.get("source_path"),
                        "file_type": metadata.get("file_type"),
                        "language": metadata.get("language", "en"),
                        "created_at": datetime.utcnow().isoformat(),
                    }
                }
                
                # Add page info if available
                if "pages" in metadata:
                    # Estimate which page this chunk belongs to
                    total_chars = metadata.get("char_count", len(text))
                    chunk_progress = char_position / total_chars if total_chars > 0 else 0
                    
                    page_estimate = int(chunk_progress * len(metadata["pages"])) + 1
                    chunk["metadata"]["page"] = min(page_estimate, len(metadata["pages"]))
                
                chunks.append(chunk)
                char_position += len(chunk_text) + 1  # +1 for spacing
            
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "create_chunks",
                duration_ms,
                success=True,
                doc_id=metadata.get("doc_id"),
                total_chunks=len(chunks),
                total_tokens=sum(c["token_count"] for c in chunks)
            )
            
            return chunks
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "create_chunks",
                duration_ms,
                success=False,
                error=str(e),
                doc_id=metadata.get("doc_id")
            )
            raise


# Import time for timing
import time