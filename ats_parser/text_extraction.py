"""Document-to-Markdown extraction, the stage that runs before structure extraction.

This module owns one question: *what does the document say?* The provider layer owns
a separate one: *what does that text mean?* Keeping them apart means a new OCR engine
only has to implement `TextExtractor` - no provider, schema, or exporter changes.

The Markdown produced here is persisted next to the parsed JSON, so it doubles as the
audit trail for an extraction and as the corpus for downstream retrieval.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
DOCX_EXTENSIONS = {".docx"}
SUPPORTED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS | DOCX_EXTENSIONS

# Mistral OCR is billed per page. Override if the published rate changes.
DEFAULT_OCR_COST_PER_PAGE_USD = 0.001

TRANSCRIPTION_PROMPT = """Transcribe this document to GitHub-flavoured Markdown.
Reproduce every page top to bottom and left to right, including multiple columns, tables,
text boxes, headers, footers, and readable text inside images or logos. Preserve the
original wording, dates, and bullet points exactly. Render section titles as Markdown
headings and tabular content as Markdown tables. Do not summarise, translate, reorder,
or add commentary. Output only the transcription."""


@dataclass(frozen=True)
class ExtractedText:
    """The Markdown form of one resume, plus a record of how it was produced."""

    markdown: str
    extractor: str
    model: str | None = None
    page_count: int | None = None


class TextExtractor(Protocol):
    def extract(self, file_path: Path) -> ExtractedText:
        """Return the Markdown transcription of one supported resume file."""


class DocxExtractor:
    """Convert a DOCX resume to Markdown locally. No API call, no cost."""

    name = "docx-local"

    def extract(self, file_path: Path) -> ExtractedText:
        document = Document(file_path)
        blocks = []
        for block in _iter_blocks(document):
            rendered = (
                _paragraph_markdown(block)
                if isinstance(block, Paragraph)
                else _table_markdown(block)
            )
            if rendered:
                blocks.append(rendered)
        markdown = "\n\n".join(blocks).strip()
        if not markdown:
            raise RuntimeError(f"No readable text found in {file_path.name}.")
        return ExtractedText(markdown=markdown, extractor=self.name)


class MistralOCRExtractor:
    """Transcribe PDF and image resumes with Mistral's hosted OCR model."""

    name = "mistral-ocr"

    def __init__(self, model: str | None = None):
        from mistralai.client import Mistral

        api_key = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            raise RuntimeError("MISTRAL_API_KEY is missing. Add it to the .env file.")
        self.client = Mistral(api_key=api_key)
        self.model = model or os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest")
        self.last_usage = None
        self.last_cost_usd = None

    def extract(self, file_path: Path) -> ExtractedText:
        response = self.client.ocr.process(model=self.model, document=_data_url_document(file_path))
        pages = getattr(response, "pages", None) or []
        markdown = "\n\n".join(
            page.markdown for page in pages if getattr(page, "markdown", None)
        ).strip()
        if not markdown:
            raise RuntimeError(f"Mistral OCR returned no readable text for {file_path.name}.")
        page_count = self._record_usage(getattr(response, "usage_info", None)) or len(pages)
        return ExtractedText(markdown, self.name, self.model, page_count or None)

    def _record_usage(self, usage_info) -> int:
        """OCR bills per page, not per token, so it reports cost without token counts."""
        pages_processed = int(getattr(usage_info, "pages_processed", 0) or 0)
        # Read at call time: .env is loaded after this module is imported.
        rate = float(os.getenv("MISTRAL_OCR_COST_PER_PAGE_USD", DEFAULT_OCR_COST_PER_PAGE_USD))
        self.last_cost_usd = round(pages_processed * rate, 6) if pages_processed else None
        return pages_processed


class GeminiTextExtractor:
    """Transcribe PDF and image resumes with Gemini's native document vision."""

    name = "gemini-vision"

    def __init__(self, model: str | None = None):
        from google import genai

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it to the .env file.")
        self.client = genai.Client(api_key=api_key)
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self.last_usage = None
        self.last_cost_usd = None

    def extract(self, file_path: Path) -> ExtractedText:
        if file_path.suffix.lower() in PDF_EXTENSIONS:
            markdown = self._transcribe_pdf(file_path)
        else:
            markdown = self._transcribe([self._image_part(file_path), TRANSCRIPTION_PROMPT])
        if not markdown:
            raise RuntimeError(f"Gemini returned no readable text for {file_path.name}.")
        return ExtractedText(markdown, self.name, self.model)

    def _transcribe_pdf(self, file_path: Path) -> str:
        uploaded = self.client.files.upload(file=str(file_path))
        try:
            return self._transcribe([self._wait_until_ready(uploaded.name), TRANSCRIPTION_PROMPT])
        finally:
            try:
                self.client.files.delete(name=uploaded.name)
            except Exception:  # Never fail a good transcription over remote cleanup.
                pass

    def _wait_until_ready(self, name: str):
        deadline = time.monotonic() + 180
        while True:
            uploaded = self.client.files.get(name=name)
            state = str(getattr(uploaded, "state", "")).upper()
            if "FAILED" in state:
                raise RuntimeError("Gemini failed to process the uploaded PDF.")
            if "PROCESSING" not in state:
                return uploaded
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out while Gemini processed the uploaded PDF.")
            time.sleep(2)

    def _transcribe(self, contents: list) -> str:
        response = self.client.models.generate_content(model=self.model, contents=contents)
        self._record_usage(getattr(response, "usage_metadata", None))
        return (response.text or "").strip()

    def _record_usage(self, usage) -> None:
        if usage is None:
            self.last_usage = self.last_cost_usd = None
            return
        prompt_tokens = getattr(usage, "prompt_token_count", None) or 0
        completion_tokens = getattr(usage, "candidates_token_count", None) or 0
        self.last_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": getattr(usage, "total_token_count", None)
            or (prompt_tokens + completion_tokens),
        }
        self.last_cost_usd = round(
            (prompt_tokens / 1_000_000) * 0.15 + (completion_tokens / 1_000_000) * 0.60, 6
        )

    @staticmethod
    def _image_part(file_path: Path):
        from google.genai import types

        mime_type, _ = mimetypes.guess_type(file_path.name)
        return types.Part.from_bytes(
            data=file_path.read_bytes(), mime_type=mime_type or "image/jpeg"
        )


class DocumentExtractor:
    """Route each file to the extractor that suits it: DOCX locally, the rest via OCR."""

    def __init__(self, ocr_extractor: TextExtractor):
        self._ocr = ocr_extractor
        self._docx = DocxExtractor()

    def extract(self, file_path: Path) -> ExtractedText:
        suffix = file_path.suffix.lower()
        if suffix in DOCX_EXTENSIONS:
            return self._docx.extract(file_path)
        if suffix in PDF_EXTENSIONS | IMAGE_EXTENSIONS:
            return self._ocr.extract(file_path)
        raise ValueError(f"Unsupported file type: {file_path.suffix}")

    @property
    def last_usage(self):
        return getattr(self._ocr, "last_usage", None)

    @property
    def last_cost_usd(self):
        return getattr(self._ocr, "last_cost_usd", None)


def create_extractor(provider_name: str, model: str | None = None) -> DocumentExtractor:
    """Build the extractor stack for a provider. Add new OCR engines here."""
    name = provider_name.lower()
    if name == "gemini":
        return DocumentExtractor(GeminiTextExtractor(model))
    if name == "mistral":
        return DocumentExtractor(MistralOCRExtractor())
    raise ValueError(f"Unsupported provider: {provider_name}. Available: gemini, mistral")


def _data_url_document(file_path: Path) -> dict:
    mime_type, _ = mimetypes.guess_type(file_path.name)
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    data_url = f"data:{mime_type or 'application/octet-stream'};base64,{encoded}"
    if file_path.suffix.lower() in PDF_EXTENSIONS:
        return {"type": "document_url", "document_url": data_url}
    return {"type": "image_url", "image_url": data_url}


def _iter_blocks(document):
    """Yield paragraphs and tables in the order they appear in the document body."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _paragraph_markdown(paragraph: Paragraph) -> str:
    text = " ".join(paragraph.text.split())
    if not text:
        return ""
    style = (paragraph.style.name if paragraph.style else "") or ""
    if style.startswith("Heading"):
        level = style[len("Heading"):].strip()
        return f"{'#' * min(int(level) if level.isdigit() else 1, 6)} {text}"
    if style.startswith("List"):
        return f"- {text}"
    return text


def _table_markdown(table: Table) -> str:
    rows = [
        [" ".join(cell.text.split()).replace("|", r"\|") for cell in row.cells]
        for row in table.rows
    ]
    rows = [row for row in rows if any(row)]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)
