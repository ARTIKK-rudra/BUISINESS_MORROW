from fastapi import APIRouter, Request, status

from app.api.dependencies import SessionDep
from app.schemas.auth import LoginRequest, PasswordResetRequest, RegisterRequest, TokenResponse
from app.services.auth import AuthService, accept_password_reset_request

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, session: SessionDep):
    return await AuthService(session).register(payload, getattr(request.state, "request_id", None))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep):
    return await AuthService(session).login(payload)


@router.post("/password-reset", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def password_reset(payload: PasswordResetRequest):
    await accept_password_reset_request(str(payload.email))
