from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass

from app.core.config import get_settings
from app.llm.service import get_raw_provider

logger = logging.getLogger("app.services.ocr")

OCR_PROMPT = (
    "Extract ALL readable text from this document page exactly as printed.\n"
    "Include headings, labels, numbers, dates, amounts, IDs, addresses, and table rows.\n"
    "Preserve paragraph and line breaks.\n"
    "Return ONLY the extracted text with no commentary or markdown fences."
)

MIN_NATIVE_TEXT_CHARS = 80
MIN_NATIVE_CHARS_PER_PAGE = 40


@dataclass
class ExtractionResult:
    text: str
    method: str  # native | ocr | mixed | none | disabled
    pages_ocrd: int = 0
    text_chars: int = 0


class OCRService:
    """Extract text from PDFs and images.

    Strategy (efficient):
    1. Try native PDF text extraction (pypdf) — free and instant.
    2. OCR only pages with sparse/no native text via NVIDIA vision model.
    3. Images always go through vision OCR.
    """

    async def extract_pdf(self, raw: bytes) -> ExtractionResult:
        settings = get_settings()
        if settings.disable_external_llm:
            native = self._native_pdf_text(raw)
            return ExtractionResult(text=native, method="disabled" if not native else "native", text_chars=len(native))

        native_pages = self._native_pdf_pages(raw)
        if not native_pages:
            return ExtractionResult(text="", method="none", text_chars=0)

        combined_native = "\n\n".join(page for page in native_pages if page)
        if len(combined_native) >= MIN_NATIVE_TEXT_CHARS and all(
            len(page) >= MIN_NATIVE_CHARS_PER_PAGE for page in native_pages if page
        ):
            return ExtractionResult(text=combined_native, method="native", text_chars=len(combined_native))

        sparse_indices = [
            index
            for index, page in enumerate(native_pages)
            if len(page.strip()) < MIN_NATIVE_CHARS_PER_PAGE
        ]
        if not sparse_indices and len(combined_native) >= MIN_NATIVE_TEXT_CHARS:
            return ExtractionResult(text=combined_native, method="native", text_chars=len(combined_native))

        if not sparse_indices:
            sparse_indices = list(range(len(native_pages)))

        page_images = self._render_pdf_pages(raw, sparse_indices, settings.ocr_max_pages)
        if not page_images:
            return ExtractionResult(
                text=combined_native,
                method="native" if combined_native else "none",
                text_chars=len(combined_native),
            )

        ocr_texts = await self._ocr_pages_parallel(page_images, settings.ocr_page_concurrency)
        merged: list[str] = []
        ocr_iter = iter(ocr_texts)
        pages_ocrd = 0
        for index, native in enumerate(native_pages):
            if index in sparse_indices:
                ocr_text = next(ocr_iter, "")
                if ocr_text.strip():
                    merged.append(ocr_text.strip())
                    pages_ocrd += 1
                elif native.strip():
                    merged.append(native.strip())
            elif native.strip():
                merged.append(native.strip())

        text = "\n\n".join(merged).strip()
        method = "mixed" if pages_ocrd and combined_native else ("ocr" if pages_ocrd else ("native" if text else "none"))
        return ExtractionResult(text=text, method=method, pages_ocrd=pages_ocrd, text_chars=len(text))

    async def extract_image(self, raw: bytes, mime_type: str | None) -> ExtractionResult:
        settings = get_settings()
        if settings.disable_external_llm:
            return ExtractionResult(text="", method="disabled", text_chars=0)

        prepared = self._prepare_image_bytes(raw, mime_type)
        text = await self._vision_ocr(prepared, mime_type or "image/jpeg")
        cleaned = text.strip()
        return ExtractionResult(
            text=cleaned,
            method="ocr" if cleaned else "none",
            pages_ocrd=1 if cleaned else 0,
            text_chars=len(cleaned),
        )

    def _native_pdf_pages(self, raw: bytes) -> list[str]:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return [(page.extract_text() or "").strip() for page in reader.pages[: get_settings().ocr_max_pages]]
        except Exception as exc:
            logger.warning("native_pdf_extract_failed error=%s", exc)
            return []

    def _native_pdf_text(self, raw: bytes) -> str:
        return "\n\n".join(page for page in self._native_pdf_pages(raw) if page)

    def _render_pdf_pages(self, raw: bytes, page_indices: list[int], max_pages: int) -> list[tuple[int, bytes, str]]:
        try:
            import pypdfium2 as pdfium
        except ImportError:
            logger.warning("pypdfium2_not_installed pdf_ocr_unavailable")
            return []

        try:
            doc = pdfium.PdfDocument(raw)
            total = min(len(doc), max_pages)
            rendered: list[tuple[int, bytes, str]] = []
            for index in page_indices:
                if index >= total:
                    continue
                page = doc[index]
                bitmap = page.render(scale=150 / 72)
                pil_image = bitmap.to_pil()
                prepared = self._prepare_image_bytes_from_pil(pil_image)
                rendered.append((index, prepared, "image/jpeg"))
            return rendered
        except Exception as exc:
            logger.warning("pdf_render_failed error=%s", exc)
            return []

    async def _ocr_pages_parallel(
        self,
        pages: list[tuple[int, bytes, str]],
        concurrency: int,
    ) -> list[str]:
        semaphore = asyncio.Semaphore(max(1, concurrency))

        async def _one(_index: int, image_bytes: bytes, mime_type: str) -> str:
            async with semaphore:
                return await self._vision_ocr(image_bytes, mime_type)

        return await asyncio.gather(*(_one(index, data, mime) for index, data, mime in pages))

    async def _vision_ocr(self, image_bytes: bytes, mime_type: str) -> str:
        settings = get_settings()
        provider_name = (settings.llm_provider or "gemini").strip().lower()
        if provider_name == "nvidia":
            from app.llm.providers.nvidia_provider import NvidiaProvider

            provider = get_raw_provider()
            if isinstance(provider, NvidiaProvider):
                try:
                    return await provider.generate_with_image(
                        OCR_PROMPT,
                        image_bytes,
                        mime_type,
                        max_tokens=settings.ocr_max_tokens,
                    )
                except Exception as exc:
                    logger.warning("nvidia_vision_ocr_failed error=%s", exc)
                    return ""
        if provider_name == "gemini" and settings.gemini_api_key:
            return await self._gemini_vision_ocr(image_bytes, mime_type)
        return ""

    async def _gemini_vision_ocr(self, image_bytes: bytes, mime_type: str) -> str:
        try:
            import google.generativeai as genai

            settings = get_settings()
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel(settings.gemini_ocr_model)
            response = model.generate_content(
                [
                    OCR_PROMPT,
                    {"mime_type": mime_type, "data": image_bytes},
                ],
                generation_config={"temperature": 0.0},
            )
            return response.text or ""
        except Exception as exc:
            logger.warning("gemini_vision_ocr_failed error=%s", exc)
            return ""

    def _prepare_image_bytes(self, raw: bytes, mime_type: str | None) -> bytes:
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(raw))
            return self._prepare_image_bytes_from_pil(image)
        except Exception:
            return raw

    def _prepare_image_bytes_from_pil(self, image) -> bytes:
        from PIL import Image

        max_side = get_settings().ocr_max_image_side
        if max(image.size) > max_side:
            ratio = max_side / max(image.size)
            new_size = (max(1, int(image.size[0] * ratio)), max(1, int(image.size[1] * ratio)))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85, optimize=True)
        return buffer.getvalue()


ocr_service = OCRService()
