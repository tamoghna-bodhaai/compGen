from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.services.seed_import import normalize_options, upsert_seed_questions, validate_question


class SeedImportTests(unittest.TestCase):
    def test_import_is_complete_and_idempotent(self) -> None:
        seed_file = ROOT_DIR / "sample_data" / "jee_definite_integrals_questions.json"
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "questions.db"
            self.assertEqual(upsert_seed_questions(seed_file, database_path), (50, 0))
            self.assertEqual(upsert_seed_questions(seed_file, database_path), (0, 50))
            with sqlite3.connect(database_path) as connection:
                count = connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
                topic = connection.execute("SELECT DISTINCT topic FROM questions").fetchone()[0]
            self.assertEqual(count, 50)
            self.assertEqual(topic, "Definite Integrals")

    def test_supported_question_shapes_are_validated_by_type(self) -> None:
        base = {
            "source_key": "shape-test", "exam": "JEE", "subject": "Mathematics", "chapter": "Calculus",
            "topic": "Definite Integrals", "primary_concept": "integration", "question_archetype": "test",
            "difficulty": 3, "source": "test", "source_reference": "test", "verification_status": "verified",
        }
        validate_question({**base, "question_type": "numerical", "question_json": {"stem": "Evaluate", "options": []}})
        validate_question({**base, "question_type": "multiple_correct_mcq", "question_json": {"stem": "Select", "options": ["A", "B"]}})
        with self.assertRaises(ValueError):
            validate_question({**base, "question_type": "single_correct_mcq", "question_json": {"stem": "Choose", "options": ["A"]}})

    def test_labelled_option_objects_are_normalized_for_import(self) -> None:
        labelled_options = [
            {"id": "a", "text": "First"}, {"id": "b", "text": "Second"},
            {"id": "c", "text": "Third"}, {"id": "d", "text": "Fourth"},
        ]
        self.assertEqual(normalize_options(labelled_options), ["First", "Second", "Third", "Fourth"])


if __name__ == "__main__":
    unittest.main()
