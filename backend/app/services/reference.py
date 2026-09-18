from __future__ import annotations

import base64
import io
from pathlib import Path

from app.core.settings import get_settings
from app.prompts.ingestion import INGESTION_SYSTEM_PROMPT, build_ingestion_prompt
from app.schemas.ingestion import ClassificationResponse
from app.services.ingestion import MAX_UPLOAD_BYTES, VISION_RENDER_DPI, _render_pdf_pages_for_vision
from app.services.openrouter import OpenRouterClient, OpenRouterError


SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/jpg"}
SUPPORTED_DOC_TYPES = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _image_to_base64(content: bytes, content_type: str | None) -> str:
    # Validate and optionally compress large images via PIL
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(content))
        # Normalize to PNG or JPEG for transport; keep within ~5MB base64 (~3.7MB raw)
        max_dim = 2048
        if max(image.size) > max_dim:
            image.thumbnail((max_dim, max_dim))
        # Preserve original mime where possible
        fmt = "PNG" if (content_type or "").endswith("png") else "JPEG"
        buffer = io.BytesIO()
        if fmt == "PNG":
            image.save(buffer, format="PNG", optimize=True)
        else:
            if image.mode in ("RGBA", "LA"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            image.save(buffer, format="JPEG", quality=85, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        return base64.b64encode(content).decode("ascii")


def _encode_images_for_llm(
    filename: str, content_type: str | None, content: bytes
) -> tuple[list[str], list[str]]:
    """
    Returns (images_b64_list, mime_list) suitable for OpenRouter image_url.
    For PDFs renders each page; for images returns single entry; for docx returns empty (text path).
    """
    suffix = Path(filename).suffix.lower()
    ctype = (content_type or "").lower()

    if suffix in {".png", ".jpg", ".jpeg", ".webp"} or ctype in SUPPORTED_IMAGE_TYPES:
        mime = "image/png" if suffix == ".png" or ctype == "image/png" else "image/jpeg"
        if suffix == ".webp" or ctype == "image/webp":
            mime = "image/webp"
        b64 = _image_to_base64(content, ctype)
        # Prefix later handled by OpenRouterClient; keep raw plus mime hint via data URL
        # Return raw b64; caller will wrap with correct mime via data URL
        # We embed mime by returning data URL directly
        return [f"data:{mime};base64,{b64}"], [mime]

    if suffix == ".pdf" or ctype == "application/pdf":
        try:
            pages = _render_pdf_pages_for_vision(content)
        except Exception as error:
            raise OpenRouterError(f"This PDF could not be rendered for reference extraction: {error}") from error
        # pages is list of (page_number, b64_png)
        images = [f"data:image/png;base64,{b64}" for _, b64 in pages]
        return images, ["image/png"] * len(images)

    # docx and others: no images
    return [], []


async def extract_reference_questions(
    filename: str,
    content_type: str | None,
    content: bytes,
    custom_instruction: str | None = None,
) -> tuple[list[dict], list[str]]:
    """
    Extracts reference questions from an uploaded image/pdf/docx using vision-capable LLM.
    Returns (reference_questions_dicts, images_for_generation)
    Each question dict matches ClassificationResponse shape (stem, options, question_type, etc.)
    """
    if not content:
        raise OpenRouterError("No file uploaded")
    if len(content) > MAX_UPLOAD_BYTES:
        raise OpenRouterError("Uploads must be 35 MB or smaller.")

    suffix = Path(filename).suffix.lower()
    ctype = (content_type or "").lower()

    # Fast path: image or PDF -> vision
    images: list[str] = []
    text_chunk: str | None = None

    if suffix in {".png", ".jpg", ".jpeg", ".webp"} or ctype in SUPPORTED_IMAGE_TYPES:
        images, _ = _encode_images_for_llm(filename, content_type, content)
        # No text extraction needed; LLM will read image
        text_chunk = f"The attached image is the reference question paper '{filename}'. Extract every clearly readable question. Custom instruction: {custom_instruction or 'None'}"
    elif suffix == ".pdf" or ctype == "application/pdf":
        # Try vision render + text fallback
        images, _ = _encode_images_for_llm(filename, content_type, content)
        # Also provide text hint if available via quick extract (optional)
        text_chunk = f"The attached images are pages of reference paper '{filename}'. Extract every clearly readable question from all pages. Custom instruction: {custom_instruction or 'None'}"
    elif suffix == ".docx" or ctype == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        # DOCX -> text extraction via ingestion helper
        from docx import Document

        document = Document(io.BytesIO(content))
        parts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            parts.extend(cell.text.strip() for row in table.rows for cell in row.cells if cell.text.strip())
        text = "\n".join(parts).strip()
        if not text:
            raise OpenRouterError("This DOCX contains no readable text.")
        text_chunk = text
        images = []
    else:
        raise OpenRouterError("Supported uploads for reference mode are PNG, JPEG, WEBP, PDF and DOCX.")

    settings = get_settings()
    primary_model = settings.classification_model or settings.generation_model
    fallback_model = settings.classification_fallback_model

    models_to_try: list[str | None] = []
    if primary_model:
        models_to_try.append(primary_model)
    if fallback_model and fallback_model not in models_to_try:
        models_to_try.append(fallback_model)
    if not models_to_try:
        models_to_try = [None]

    client = OpenRouterClient(settings)

    # Build prompt: reuse ingestion prompt structure but emphasize reference extraction
    system_prompt = INGESTION_SYSTEM_PROMPT
    source_name = filename or "reference-paper"
    conversion_note = (custom_instruction or "").strip() or "Extract reference questions as-is for structural variation. Auto-detect JEE/NEET, subject, chapter, topic."

    # For image/PDF vision, the text_chunk is just instruction; for docx it's actual text
    if images:
        user_prompt = build_ingestion_prompt(
            source_name=source_name, conversion_note=conversion_note, source_text=text_chunk or ""
        )
    else:
        user_prompt = build_ingestion_prompt(
            source_name=source_name, conversion_note=conversion_note, source_text=text_chunk or ""
        )

    last_error: Exception | None = None
    for attempt_model in models_to_try:
        try:
            response = await client.call_llm(
                model=attempt_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=ClassificationResponse.model_json_schema(),
                temperature=0.1,
                max_tokens=8000,
                images=images if images else None,
            )
            validated = ClassificationResponse.model_validate(response)
            # Convert to list of dicts suitable for generation seeds
            refs = []
            for q in validated.questions:
                refs.append(
                    {
                        "source_question_number": q.source_question_number,
                        "exam": q.exam,
                        "subject": q.subject,
                        "chapter": q.chapter,
                        "topic": q.topic,
                        "subtopic": q.subtopic,
                        "question_type": q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type),
                        "difficulty": q.difficulty,
                        "stem": q.stem,
                        "options": q.options,
                        "correct_answer": q.correct_answer,
                        "solution": q.solution,
                        "primary_concept": q.primary_concept,
                        "question_archetype": q.question_archetype,
                    }
                )
            return refs, images
        except Exception as error:
            last_error = error
            if attempt_model == models_to_try[-1]:
                break
            continue

    if isinstance(last_error, OpenRouterError):
        raise last_error
    if last_error:
        raise OpenRouterError(str(last_error)) from last_error
    raise OpenRouterError("Reference extraction failed with no response.")
