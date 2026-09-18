from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from fastapi.responses import FileResponse

from app.schemas.papers import (
    AddManualQuestionRequest,
    LockRequest,
    PaperCreateRequest,
    PaperExportRequest,
    PaperUpdateRequest,
    QuestionEditRequest,
    RegenerateSelectedRequest,
    SectionCreateRequest,
    SectionUpdateRequest,
)
from app.services.generation import GenerationFailure
from app.services.document_renderer import DocumentRenderError, PaperDocumentRenderer
from app.services.branding import BrandingProfileService
from app.services.openrouter import ModelConfigurationError
from app.services.papers import PaperConflictError, PaperNotFoundError, PaperService
from app.services.retrieval import RetrievalError

router = APIRouter(prefix="/api/papers", tags=["papers"])


def _raise(error: Exception) -> None:
    if isinstance(error, PaperNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, PaperConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if isinstance(error, ModelConfigurationError):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    if isinstance(error, (GenerationFailure, RetrievalError)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    if isinstance(error, DocumentRenderError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    raise error


@router.get("")
def list_papers() -> dict:
    return {"items": PaperService().list()}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_paper(request: PaperCreateRequest) -> dict:
    return PaperService().create(request)


@router.get("/{paper_id}")
def get_paper(paper_id: str) -> dict:
    try:
        return PaperService().get(paper_id)
    except PaperNotFoundError as error:
        _raise(error)


@router.put("/{paper_id}")
def update_paper(paper_id: str, request: PaperUpdateRequest) -> dict:
    try:
        return PaperService().update(paper_id, request)
    except PaperNotFoundError as error:
        _raise(error)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_paper(paper_id: str) -> Response:
    try:
        PaperService().delete(paper_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except PaperNotFoundError as error:
        _raise(error)


async def _run_initial_generation(paper_id: str, job_id: str) -> None:
    await PaperService().run_initial_generation_job(paper_id, job_id)


async def _run_solution_generation(paper_id: str, job_id: str) -> None:
    await PaperService().run_solution_generation_job(paper_id, job_id)


@router.post("/{paper_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_paper(paper_id: str, background_tasks: BackgroundTasks) -> dict:
    try:
        job = PaperService().queue_initial_generation(paper_id)
        background_tasks.add_task(_run_initial_generation, paper_id, job["id"])
        return {"job": job}
    except (PaperNotFoundError, PaperConflictError, ModelConfigurationError, GenerationFailure, RetrievalError) as error:
        _raise(error)


@router.post("/{paper_id}/solutions/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_solutions(paper_id: str, background_tasks: BackgroundTasks) -> dict:
    try:
        job = PaperService().queue_solution_generation(paper_id)
        background_tasks.add_task(_run_solution_generation, paper_id, job["id"])
        return {"job": job}
    except (PaperNotFoundError, PaperConflictError, ModelConfigurationError, GenerationFailure, RetrievalError) as error:
        _raise(error)


@router.post("/{paper_id}/generation/pause")
def pause_generation(paper_id: str) -> dict:
    try:
        return {"job": PaperService().pause_generation(paper_id)}
    except (PaperNotFoundError, PaperConflictError) as error:
        _raise(error)


@router.post("/{paper_id}/generation/resume")
def resume_generation(paper_id: str) -> dict:
    try:
        return {"job": PaperService().resume_generation(paper_id)}
    except (PaperNotFoundError, PaperConflictError) as error:
        _raise(error)


@router.post("/{paper_id}/generation/cancel")
def cancel_generation(paper_id: str) -> dict:
    try:
        return {"job": PaperService().cancel_generation(paper_id)}
    except (PaperNotFoundError, PaperConflictError) as error:
        _raise(error)


@router.post("/{paper_id}/sections")
def add_section(paper_id: str, request: SectionCreateRequest) -> dict:
    try:
        return PaperService().add_section(paper_id, request.title)
    except PaperNotFoundError as error:
        _raise(error)


@router.put("/{paper_id}/sections/{section_id}")
def update_section(paper_id: str, section_id: str, request: SectionUpdateRequest) -> dict:
    try:
        return PaperService().update_section(paper_id, section_id, title=request.title, position=request.position)
    except PaperNotFoundError as error:
        _raise(error)


@router.delete("/{paper_id}/sections/{section_id}")
def delete_section(paper_id: str, section_id: str) -> dict:
    try:
        return PaperService().delete_section(paper_id, section_id)
    except PaperNotFoundError as error:
        _raise(error)


@router.post("/{paper_id}/questions/manual", status_code=status.HTTP_201_CREATED)
def add_manual_question(paper_id: str, request: AddManualQuestionRequest) -> dict:
    try:
        return PaperService().add_manual_question(paper_id, request)
    except PaperNotFoundError as error:
        _raise(error)


@router.put("/{paper_id}/questions/{question_id}")
def edit_question(paper_id: str, question_id: str, request: QuestionEditRequest) -> dict:
    try:
        return PaperService().edit_question(paper_id, question_id, request)
    except (PaperNotFoundError, PaperConflictError) as error:
        _raise(error)


@router.get("/{paper_id}/questions/{question_id}/seeds")
def get_question_seeds(paper_id: str, question_id: str) -> dict:
    try:
        return PaperService().get_question_seeds(paper_id, question_id)
    except (PaperNotFoundError, PaperConflictError) as error:
        _raise(error)


@router.put("/{paper_id}/questions/{question_id}/lock")
def lock_question(paper_id: str, question_id: str, request: LockRequest) -> dict:
    try:
        return PaperService().set_lock(paper_id, question_id, request.locked)
    except PaperNotFoundError as error:
        _raise(error)


@router.delete("/{paper_id}/questions/{question_id}")
def delete_question(paper_id: str, question_id: str) -> dict:
    try:
        return PaperService().delete_question(paper_id, question_id)
    except PaperNotFoundError as error:
        _raise(error)


@router.post("/{paper_id}/regenerate-selected")
async def regenerate_selected(paper_id: str, request: RegenerateSelectedRequest) -> dict:
    try:
        return await PaperService().regenerate_questions(paper_id, request.question_ids, custom_instruction=request.custom_instruction)
    except (PaperNotFoundError, PaperConflictError, ModelConfigurationError, GenerationFailure, RetrievalError) as error:
        _raise(error)


@router.post("/{paper_id}/regenerate-unlocked")
async def regenerate_unlocked(paper_id: str) -> dict:
    try:
        return await PaperService().regenerate_unlocked(paper_id)
    except (PaperNotFoundError, PaperConflictError, ModelConfigurationError, GenerationFailure, RetrievalError) as error:
        _raise(error)


def _cleanup_export(path: Path) -> None:
    path.unlink(missing_ok=True)
    if path.suffix == ".pdf":
        path.with_suffix(".docx").unlink(missing_ok=True)


@router.post("/{paper_id}/export")
def export_paper(paper_id: str, request: PaperExportRequest, background_tasks: BackgroundTasks) -> FileResponse:
    try:
        paper = PaperService().get(paper_id)
        template_id = request.branding_template_id if request.branding_template_id is not None else paper.get("branding_template_id")
        resolved_branding = BrandingProfileService().resolve(template_id, paper.get("branding_config"))
        paper["branding_config"] = {**resolved_branding, **(request.branding_overrides or {})}
        path, media_type = PaperDocumentRenderer().export(paper, output_format=request.format, variant=request.variant)
        background_tasks.add_task(_cleanup_export, path)
        return FileResponse(path, media_type=media_type, filename=path.name, background=background_tasks)
    except (PaperNotFoundError, DocumentRenderError) as error:
        _raise(error)
