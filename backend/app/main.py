from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.branding import router as branding_router
from app.api.generation import router as generation_router
from app.api.papers import router as papers_router
from app.api.questions import router as questions_router
from app.db.database import initialize_database
from app.services.ingestion import QuestionIngestionService
from app.services.papers import PaperService

app = FastAPI(
    title="Question Paper Generator API",
    version="0.1.0",
    description="Foundation API for curated question-bank ingestion and retrieval.",
)
app.include_router(questions_router)
app.include_router(generation_router)
app.include_router(papers_router)
app.include_router(branding_router)


@app.on_event("startup")
def startup() -> None:
    initialize_database()
    PaperService.recover_interrupted_generation_jobs()
    QuestionIngestionService.recover_interrupted_jobs()


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


# Keep the teacher workspace dependency-free: FastAPI serves this small static
# application in development and production alike. Mount it last so /api and
# /docs keep their normal routes.
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
