"""Content ingest layer with plugin architecture.

Each input type (URL, PDF, text, ...) has a chain of backends.
The first successful backend wins; failures cascade to the next.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import trafilatura
import pdfplumber

from mediaforge.types import Source, SourceType, IngestResult


# ── Exceptions ────────────────────────────────────────────

class IngestError(Exception):
    """All registered backends failed for a source."""
    pass


class IngestBackendError(Exception):
    """Single backend failure — should trigger fallback."""
    pass


# ── Backend Interface ─────────────────────────────────────

class IngesterBackend(ABC):
    """One backend in the ingest chain."""

    @abstractmethod
    def ingest(self, source: Source) -> str:
        """Extract markdown content. Raise IngestBackendError on failure."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'trafilatura'."""
        ...


# ── URL Backend ───────────────────────────────────────────

class TrafilaturaIngester(IngesterBackend):
    """Extract clean text from web pages using trafilatura."""

    name = "trafilatura"

    def ingest(self, source: Source) -> str:
        downloaded = trafilatura.fetch_url(source.content)
        if downloaded is None:
            raise IngestBackendError(f"Failed to fetch {source.content}")

        text = trafilatura.extract(
            downloaded,
            output_format="markdown",
            with_metadata=True,
            include_tables=True,
        )
        if not text:
            raise IngestBackendError(f"No extractable content from {source.content}")

        return text


# ── PDF Backend ───────────────────────────────────────────

class PDFPlumberIngester(IngesterBackend):
    """Extract text from PDF using pdfplumber."""

    name = "pdfplumber"

    def ingest(self, source: Source) -> str:
        try:
            with pdfplumber.open(source.content) as pdf:
                pages = []
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages.append(text)
                if not pages:
                    raise IngestBackendError(f"No text in PDF: {source.content}")
                return "\n\n".join(pages)
        except Exception as e:
            raise IngestBackendError(f"PDF parse failed: {e}") from e


# ── Text Backend ──────────────────────────────────────────

class TextIngester(IngesterBackend):
    """Pass-through for raw text."""

    name = "passthrough"

    def ingest(self, source: Source) -> str:
        return source.content


# ── Registry ──────────────────────────────────────────────

# Priority-ordered backend chains per source type.
BACKEND_REGISTRY: dict[SourceType, list[IngesterBackend]] = {
    SourceType.URL:  [TrafilaturaIngester()],
    SourceType.PDF:  [PDFPlumberIngester()],
    SourceType.TEXT: [TextIngester()],
    # Future: OFFICE → MarkItDown, IMAGE → MinerU OCR, CUA_SESSION → CUA parser
}


# ── Ingester ──────────────────────────────────────────────

class Ingester:
    """Route sources through backend chains, cascade on failure."""

    def ingest(self, sources: list[Source]) -> IngestResult:
        """Ingest multiple sources, concatenating results."""
        warnings: list[str] = []
        parts: list[str] = []
        backend_used: str = ""
        total_confidence: float = 1.0

        for source in sources:
            result = self._ingest_one(source)
            parts.append(result.content)
            if result.warnings:
                warnings.extend(result.warnings)
            backend_used = result.backend_used  # last one wins for display
            total_confidence = min(total_confidence, result.confidence)

        return IngestResult(
            content="\n\n---\n\n".join(parts),
            backend_used=backend_used,
            confidence=total_confidence,
            warnings=warnings,
        )

    def _ingest_one(self, source: Source) -> IngestResult:
        chains = BACKEND_REGISTRY.get(source.type, [])
        if not chains:
            return IngestResult(
                content=source.content,
                backend_used="passthrough",
                confidence=0.0,
                warnings=[f"No backend for type {source.type}"],
            )

        errors: list[str] = []
        for backend in chains:
            try:
                content = backend.ingest(source)
                return IngestResult(
                    content=content,
                    backend_used=backend.name,
                    confidence=1.0,
                )
            except IngestBackendError as e:
                errors.append(f"{backend.name}: {e}")

        raise IngestError(
            f"All backends failed for {source.type} source. Errors: {'; '.join(errors)}"
        )
