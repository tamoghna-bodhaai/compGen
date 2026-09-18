from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.api.questions import list_questions
from app.services.ingestion import MAX_UPLOAD_BYTES, IngestionError, QuestionIngestionService, _best_pdf_pages, extract_source


CLASSIFIED_RESPONSE = {
    "questions": [{
        "source_question_number": 1,
        "source_page": 2,
        "exam": "JEE",
        "class_level": "Class 12",
        "subject": "Mathematics",
        "chapter": "Calculus",
        "topic": "Definite Integrals",
        "subtopic": "Properties of definite integrals",
        "primary_concept": "Definite integration",
        "secondary_concepts": ["symmetry"],
        "question_archetype": "evaluate_integral",
        "question_type": "single_correct_mcq",
        "difficulty": 3,
        "stem": "Evaluate $\\int_0^1 x\\,dx$.",
        "options": ["$0$", "$1/2$", "$1$", "$2$"],
        "correct_answer": "B",
        "solution": None,
        "expected_time_minutes": 2,
        "marks": 4,
    }],
}


class QuestionIngestionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "questions.db"
        self.previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{self.database_path}"

    def tearDown(self) -> None:
        if self.previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.previous_database_url
        self.temporary_directory.cleanup()

    async def test_pasted_question_is_classified_and_stored_as_a_seed(self) -> None:
        with patch("app.services.ingestion.OpenRouterClient.call_llm", new=AsyncMock(return_value=CLASSIFIED_RESPONSE)) as call:
            result = await QuestionIngestionService().ingest(
                filename="practice-set.txt",
                content_type="text/plain",
                content=b"",
                source_text="1. Evaluate the integral.",
                conversion_note="Classify this as JEE Mathematics.",
            )
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["verification_status"], "pending_review")
        self.assertEqual(call.await_count, 1)
        stored = list_questions(exam="JEE", subject="Mathematics", topic="Definite Integrals")
        self.assertEqual(stored["count"], 1)
        self.assertEqual(stored["items"][0]["question_json"]["options"], CLASSIFIED_RESPONSE["questions"][0]["options"])
        self.assertEqual(stored["items"][0]["verification_status"], "pending_review")

    def test_extract_source_accepts_pasted_text_and_rejects_unknown_uploads(self) -> None:
        source = extract_source(filename="pasted.txt", content_type="text/plain", content=b"", source_text="A question")
        self.assertEqual(source.pages, [(None, "A question")])
        with self.assertRaises(IngestionError):
            extract_source(filename="questions.png", content_type="image/png", content=b"png", source_text="")

    def test_upload_limit_is_35_mb(self) -> None:
        with self.assertRaisesRegex(IngestionError, "35 MB"):
            extract_source(filename="questions.pdf", content_type="application/pdf", content=b"x" * (MAX_UPLOAD_BYTES + 1), source_text="")

    async def test_ingestion_job_persists_progress_and_completion(self) -> None:
        service = QuestionIngestionService()
        job = service.create_job("practice.txt")
        with patch("app.services.ingestion.OpenRouterClient.call_llm", new=AsyncMock(return_value=CLASSIFIED_RESPONSE)):
            await service.run_job(job["id"], filename="practice.txt", content_type="text/plain", content=b"", source_text="1. Evaluate the integral.", conversion_note="")
        completed = service.get_job(job["id"])
        self.assertEqual(completed["state"], "succeeded")
        self.assertEqual(completed["phase"], "complete")
        self.assertEqual(completed["total_chunks"], 1)
        self.assertEqual(completed["completed_chunks"], 1)
        self.assertEqual(completed["ingested_questions"], 1)

    def test_scanned_pdf_uses_ocr_after_both_text_extractors_are_empty(self) -> None:
        with (
            patch("app.services.ingestion._extract_pdf_with_pypdf", return_value=[(1, "")]),
            patch("app.services.ingestion._extract_pdf_with_pymupdf", return_value=[(1, "")]),
            patch("app.services.ingestion._extract_pdf_with_ocr", return_value=[(1, "1. OCR question text")]) as ocr,
        ):
            pages = _best_pdf_pages(b"scanned-pdf")

        self.assertEqual(pages, [(1, "1. OCR question text")])
        ocr.assert_called_once_with(b"scanned-pdf")
