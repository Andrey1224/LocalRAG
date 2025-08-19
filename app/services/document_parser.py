"""Document parsing services for different file formats."""

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from docx import Document
from langdetect import LangDetectError, detect
from PyPDF2 import PdfReader

from app.core.config import app_config
from app.core.logging import ServiceLogger


class DocumentParser:
    """Base document parser with common functionality."""

    def __init__(self):
        self.logger = ServiceLogger("document_parser")
        ingest_config = app_config.ingest
        self.supported_formats = ingest_config.get(
            "supported_formats", [".pdf", ".md", ".html", ".txt", ".docx"]
        )
        self.max_file_size = (
            ingest_config.get("max_file_size_mb", 50) * 1024 * 1024
        )  # Convert to bytes
        self.max_chunks_per_doc = ingest_config.get("max_chunks_per_document", 2000)

    def is_supported_format(self, file_path: str) -> bool:
        """Check if file format is supported."""
        path = Path(file_path)
        return path.suffix.lower() in self.supported_formats

    def is_url(self, path: str) -> bool:
        """Check if path is a URL."""
        parsed = urlparse(path)
        return parsed.scheme in ["http", "https"]

    async def download_file(self, url: str) -> bytes:
        """Download file from URL."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            # Check content length
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.max_file_size:
                raise ValueError(f"File too large: {content_length} bytes")

            content = response.content
            if len(content) > self.max_file_size:
                raise ValueError(f"File too large: {len(content)} bytes")

            return content

    def read_local_file(self, file_path: str) -> bytes:
        """Read local file."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if path.stat().st_size > self.max_file_size:
            raise ValueError(f"File too large: {path.stat().st_size} bytes")

        return path.read_bytes()

    def calculate_content_hash(self, content: bytes) -> str:
        """Calculate SHA-256 hash of content."""
        return hashlib.sha256(content).hexdigest()

    def detect_language(self, text: str) -> str:
        """Detect text language."""
        try:
            # Use first 1000 characters for detection
            sample = text[:1000].strip()
            if len(sample) < 10:
                return "en"  # Default to English for short texts

            lang = detect(sample)
            return lang if lang in ["en", "ru", "es", "fr", "de"] else "en"
        except LangDetectError:
            return "en"  # Default to English if detection fails

    def normalize_text(self, text: str) -> str:
        """Normalize text content."""
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)

        # Remove multiple newlines
        text = re.sub(r"\n+", "\n", text)

        # Remove leading/trailing whitespace
        text = text.strip()

        return text


class PDFParser(DocumentParser):
    """PDF document parser."""

    def parse_pdf(self, content: bytes) -> tuple[str, dict]:
        """Parse PDF content."""
        import io

        try:
            pdf_file = io.BytesIO(content)
            pdf_reader = PdfReader(pdf_file)

            # Check if PDF is encrypted
            if pdf_reader.is_encrypted:
                raise ValueError("PDF is password protected")

            text_parts = []
            metadata = {
                "total_pages": len(pdf_reader.pages),
                "title": pdf_reader.metadata.title if pdf_reader.metadata else None,
                "author": pdf_reader.metadata.author if pdf_reader.metadata else None,
                "pages": [],
            }

            for page_num, page in enumerate(pdf_reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    normalized_text = self.normalize_text(page_text)

                    if normalized_text:
                        text_parts.append(normalized_text)
                        metadata["pages"].append(
                            {"page": page_num, "char_count": len(normalized_text)}
                        )

                except Exception as e:
                    self.logger.log_operation(
                        "pdf_page_parse", 0, success=False, error=f"Page {page_num}: {str(e)}"
                    )
                    continue

            full_text = "\n\n".join(text_parts)
            return full_text, metadata

        except Exception as e:
            raise ValueError(f"PDF parsing failed: {str(e)}")


class MarkdownParser(DocumentParser):
    """Markdown document parser."""

    def parse_markdown(self, content: bytes) -> tuple[str, dict]:
        """Parse Markdown content."""
        try:
            text = content.decode("utf-8")

            # Extract title from first # header
            title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            title = title_match.group(1) if title_match else None

            # Remove markdown syntax for clean text
            # Remove headers
            text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

            # Remove code blocks
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            text = re.sub(r"`([^`]+)`", r"\1", text)

            # Remove links but keep text
            text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

            # Remove emphasis
            text = re.sub(r"\*\*([^\*]+)\*\*", r"\1", text)
            text = re.sub(r"\*([^\*]+)\*", r"\1", text)

            # Remove lists markers
            text = re.sub(r"^\s*[-\*\+]\s+", "", text, flags=re.MULTILINE)
            text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

            normalized_text = self.normalize_text(text)

            metadata = {"title": title, "format": "markdown", "char_count": len(normalized_text)}

            return normalized_text, metadata

        except UnicodeDecodeError:
            raise ValueError("Unable to decode markdown file as UTF-8")


class HTMLParser(DocumentParser):
    """HTML document parser."""

    def parse_html(self, content: bytes) -> tuple[str, dict]:
        """Parse HTML content."""
        try:
            # Try to decode as UTF-8 first, then fallback to other encodings
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")

            soup = BeautifulSoup(text, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Extract title
            title_tag = soup.find("title")
            title = title_tag.get_text() if title_tag else None

            # Extract text from body or entire document
            body = soup.find("body")
            if body:
                text_content = body.get_text()
            else:
                text_content = soup.get_text()

            normalized_text = self.normalize_text(text_content)

            metadata = {"title": title, "format": "html", "char_count": len(normalized_text)}

            return normalized_text, metadata

        except Exception as e:
            raise ValueError(f"HTML parsing failed: {str(e)}")


class TextParser(DocumentParser):
    """Plain text document parser."""

    def parse_text(self, content: bytes) -> tuple[str, dict]:
        """Parse plain text content."""
        try:
            # Try multiple encodings
            for encoding in ["utf-8", "latin-1", "cp1252"]:
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError("Unable to decode text file")

            normalized_text = self.normalize_text(text)

            # Extract potential title from first line
            lines = normalized_text.split("\n")
            title = lines[0][:100] if lines and len(lines[0].strip()) > 0 else None

            metadata = {
                "title": title,
                "format": "text",
                "char_count": len(normalized_text),
                "line_count": len(lines),
            }

            return normalized_text, metadata

        except Exception as e:
            raise ValueError(f"Text parsing failed: {str(e)}")


class DocxParser(DocumentParser):
    """Microsoft Word document parser."""

    def parse_docx(self, content: bytes) -> tuple[str, dict]:
        """Parse DOCX content."""
        import io

        try:
            docx_file = io.BytesIO(content)
            doc = Document(docx_file)

            # Extract text from paragraphs
            paragraphs = []
            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if text:
                    paragraphs.append(text)

            full_text = "\n\n".join(paragraphs)
            normalized_text = self.normalize_text(full_text)

            # Try to get title from document properties
            title = None
            if doc.core_properties.title:
                title = doc.core_properties.title
            elif paragraphs:
                # Use first paragraph as title if it's short
                first_para = paragraphs[0]
                if len(first_para) < 100:
                    title = first_para

            metadata = {
                "title": title,
                "author": doc.core_properties.author,
                "format": "docx",
                "char_count": len(normalized_text),
                "paragraph_count": len(paragraphs),
            }

            return normalized_text, metadata

        except Exception as e:
            raise ValueError(f"DOCX parsing failed: {str(e)}")


class UniversalDocumentParser:
    """Universal document parser that handles all supported formats."""

    def __init__(self):
        self.pdf_parser = PDFParser()
        self.markdown_parser = MarkdownParser()
        self.html_parser = HTMLParser()
        self.text_parser = TextParser()
        self.docx_parser = DocxParser()
        self.logger = ServiceLogger("universal_parser")

    async def parse_document(self, file_path: str) -> dict:
        """Parse document from file path or URL."""
        start_time = time.time()

        try:
            # Determine if it's a URL or local file
            if self.pdf_parser.is_url(file_path):
                content = await self.pdf_parser.download_file(file_path)
                source_type = "url"
            else:
                content = self.pdf_parser.read_local_file(file_path)
                source_type = "file"

            # Calculate content hash
            content_hash = self.pdf_parser.calculate_content_hash(content)

            # Determine file type
            path = Path(file_path)
            file_extension = path.suffix.lower()

            # Parse based on file type
            if file_extension == ".pdf":
                text, metadata = self.pdf_parser.parse_pdf(content)
            elif file_extension == ".md":
                text, metadata = self.markdown_parser.parse_markdown(content)
            elif file_extension in [".html", ".htm"]:
                text, metadata = self.html_parser.parse_html(content)
            elif file_extension == ".docx":
                text, metadata = self.docx_parser.parse_docx(content)
            elif file_extension == ".txt":
                text, metadata = self.text_parser.parse_text(content)
            else:
                raise ValueError(f"Unsupported file format: {file_extension}")

            # Detect language
            language = self.pdf_parser.detect_language(text)

            # Compile final result
            result = {
                "source_path": file_path,
                "source_type": source_type,
                "content_hash": content_hash,
                "file_type": file_extension,
                "language": language,
                "text": text,
                "metadata": metadata,
                "file_size_bytes": len(content),
                "char_count": len(text),
            }

            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "parse_document",
                duration_ms,
                success=True,
                file_type=file_extension,
                file_size=len(content),
                char_count=len(text),
            )

            return result

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_operation(
                "parse_document", duration_ms, success=False, error=str(e), file_path=file_path
            )
            raise


# Import time for timing
import time
