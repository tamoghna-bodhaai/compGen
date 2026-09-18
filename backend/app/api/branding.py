from fastapi import APIRouter

from app.schemas.papers import BrandingProfileRequest
from app.services.branding import BrandingProfileService

router = APIRouter(prefix="/api/branding-profiles", tags=["branding"])


@router.get("")
def list_branding_profiles() -> dict:
    return {"items": BrandingProfileService().list()}


@router.post("")
def save_branding_profile(request: BrandingProfileRequest) -> dict:
    return BrandingProfileService().save(request.name, request.branding_config)
