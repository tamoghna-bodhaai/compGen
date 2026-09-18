from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrontendAssetTests(unittest.TestCase):
    def test_browser_editor_assets_exist_and_target_paper_api(self) -> None:
        index = (ROOT / "frontend" / "index.html").read_text()
        app = (ROOT / "frontend" / "app.js").read_text()

        self.assertIn('src="/app.js"', index)
        self.assertIn('"/papers"', app)
        self.assertIn('"/questions/catalog"', app)
        self.assertIn('"export-paper"', app)

    def test_dashboard_is_a_filterable_paper_library_with_targeted_actions(self) -> None:
        app = (ROOT / "frontend" / "app.js").read_text()
        styles = (ROOT / "frontend" / "styles.css").read_text()

        self.assertIn('dashboardFilter', app)
        self.assertIn('dashboard-search', app)
        self.assertIn('paper-library-grid', app)
        self.assertIn('data-action="dashboard-retry"', app)
        self.assertIn('data-action="dashboard-export"', app)
        self.assertIn('data-action="generation-pause"', app)
        self.assertIn('data-action="generation-resume"', app)
        self.assertIn('data-action="generation-cancel"', app)
        self.assertIn('Generate ${remaining} remaining', app)
        self.assertIn('async function exportPaper(format, variant = "question_paper", paperId = state.paper?.id)', app)
        self.assertNotIn('class="nav-caption">Your papers', app)
        self.assertIn('.mobile-nav { display: none; }', styles)
        self.assertIn('.paper-library-grid', styles)

    def test_dashboard_redesign_preserves_interaction_hooks_and_accessibility(self) -> None:
        app = (ROOT / "frontend" / "app.js").read_text()
        styles = (ROOT / "frontend" / "styles.css").read_text()

        self.assertIn('const ICON_PATHS', app)
        self.assertIn('aria-labelledby="paper-library-heading"', app)
        self.assertIn('aria-label="Filter papers by status"', app)
        self.assertIn('id="dashboard-search"', app)
        self.assertIn('data-action="dashboard"', app)
        self.assertIn('data-action="question-bank"', app)
        self.assertIn('data-action="new-paper"', app)
        self.assertIn('data-action="dashboard-filter"', app)
        self.assertIn('data-action="dashboard-retry"', app)
        self.assertIn('data-action="dashboard-export"', app)
        self.assertIn('@media (prefers-reduced-motion: reduce)', styles)
        self.assertIn(':focus-visible', styles)
        self.assertIn('.mobile-nav button.active', styles)

    def test_question_bank_and_creator_use_separate_hash_routes(self) -> None:
        app = (ROOT / "frontend" / "app.js").read_text()

        self.assertIn('path === "/question-bank"', app)
        self.assertIn('path === "/new-paper"', app)
        self.assertIn('navigate("/question-bank")', app)
        self.assertIn('data-action="add-source-bank"', app)
        self.assertIn('data-plan-count', app)
        self.assertIn('data-plan-difficulty', app)
        self.assertIn('data-plan-field', app)
        self.assertIn('subtopic_plans', app)
        self.assertIn('data-action="ingest-questions"', app)
        self.assertIn('id="ingestion-form"', app)
        self.assertIn('ingestion-jobs', app)
        self.assertIn('activeIngestion', app)
        self.assertIn('taxonomy-tree', app)
        self.assertIn('bank-open-question', app)
        self.assertIn('loadBankQuestions', app)
        self.assertIn('data-action="bank-back"', app)
        self.assertIn('function parentBankSelection', app)
        self.assertIn('state.bankSelection = parentBankSelection()', app)
        self.assertNotIn('Browse labeled seed questions', app)

    def test_creator_subtopic_options_stay_selectable(self) -> None:
        app = (ROOT / "frontend" / "app.js").read_text()

        # Subtopic seed counts must be scoped to the selected chapters, not to the
        # already-selected subtopics — otherwise every unselected subtopic reads as
        # "0 seeds", renders disabled, and traps the paper at a single subtopic.
        self.assertIn('chapterScopedRows', app)
        self.assertIn('availability(chapterScopedRows.filter((item) => item.topic === row.topic', app)
        self.assertNotIn('availability(baseRows.filter((item) => item.topic === row.topic', app)

    def test_answer_key_renders_math_answers_and_repairs_legacy_latex(self) -> None:
        app = (ROOT / "frontend" / "app.js").read_text()

        self.assertIn('renderMath(answer)', app)
        self.assertIn(r'.replace(/\u0007(?=sqrt(?:\b|\d))/g, "\\")', app)

    def test_inspector_has_live_preview_and_custom_regeneration_instruction(self) -> None:
        app = (ROOT / "frontend" / "app.js").read_text()
        self.assertIn("Unsaved preview", app)
        self.assertIn("CUSTOM REGENERATION INSTRUCTION", app)
        self.assertIn("custom_instruction", app)


if __name__ == "__main__":
    unittest.main()
