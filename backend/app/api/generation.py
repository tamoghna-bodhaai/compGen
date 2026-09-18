from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas.generation import GenerationRequest, GenerationResponse
from app.services.generation import GenerationFailure, GenerationService
from app.services.openrouter import ModelConfigurationError
from app.services.retrieval import RetrievalError

router = APIRouter(prefix="/api/generation", tags=["generation"])


@router.post("/questions", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
async def generate_questions(request: GenerationRequest) -> GenerationResponse:
    try:
        return await GenerationService().generate(request)
    except ModelConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except RetrievalError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except GenerationFailure as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
