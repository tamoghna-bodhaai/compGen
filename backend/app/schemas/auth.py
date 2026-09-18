from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    access_code: str = Field(pattern=r"^\d{5}$")


class SessionUser(BaseModel):
    email: str


class SessionResponse(BaseModel):
    authenticated: bool
    user: SessionUser | None = None
