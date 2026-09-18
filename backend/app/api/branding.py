from fastapi import APIRouter, HTTPException, Response, status

from app.schemas.papers import BrandingProfileRequest, BrandingProfileUpdateRequest
from app.services.branding import BrandingProfileService

router = APIRouter(prefix="/api/branding-profiles", tags=["branding"])


@router.get("")
def list_branding_profiles() -> dict:
    return {"items": BrandingProfileService().list()}


@router.post("")
def save_branding_profile(request: BrandingProfileRequest) -> dict:
    return BrandingProfileService().save(request.name, request.branding_config)


@router.get("/{profile_id}")
def get_branding_profile(profile_id: str) -> dict:
    profile = BrandingProfileService().get(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branding template not found")
    return profile


@router.put("/{profile_id}")
def update_branding_profile(profile_id: str, request: BrandingProfileUpdateRequest) -> dict:
    profile = BrandingProfileService().update(profile_id, request.name, request.branding_config)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branding template not found")
    return profile


@router.post("/{profile_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_branding_profile(profile_id: str) -> dict:
    profile = BrandingProfileService().duplicate(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branding template not found")
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branding_profile(profile_id: str) -> Response:
    if not BrandingProfileService().delete(profile_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branding template not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
