"""Authentication API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from api.auth import (
    UserRole,
    authenticate_user,
    create_access_token,
    create_session,
    get_user_from_token,
    has_permission,
    list_active_sessions,
    record_audit,
)
from security import RateLimiter

router = APIRouter(prefix="/auth", tags=["authentication"])


def _get_rate_limiter(request: Request) -> RateLimiter:
    """Get or create the auth rate limiter from app state."""
    if not hasattr(request.app.state, "auth_rate_limiter"):
        request.app.state.auth_rate_limiter = RateLimiter(
            default_capacity=5.0,
            default_refill_rate=5.0 / 60.0,
        )
    return request.app.state.auth_rate_limiter


class LoginRequest(BaseModel):
    """Login request."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = 1800
    role: str


@router.post("/login")
async def login(request: Request, credentials: LoginRequest) -> TokenResponse:
    """Authenticate and receive an access token.

    Rate limited: 5 attempts per 60 seconds per IP address.
    """
    client_ip = request.client.host if request.client else "unknown"
    limiter = _get_rate_limiter(request)
    allowed, retry_after = limiter.check(f"login:{client_ip}")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {int(retry_after)} seconds.",
            headers={"Retry-After": str(int(retry_after))},
        )

    user = authenticate_user(credentials.username, credentials.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token(user)
    session = create_session(
        user,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent", ""),
    )
    record_audit(user, "LOGIN", "auth", f"session={session.session_id}", ip=client_ip)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=1800,
        role=user.role.value,
    )


@router.post("/logout")
async def logout(request: Request) -> dict:
    """Logout and invalidate the session."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        user = get_user_from_token(token)
        record_audit(user, "LOGOUT", "auth", ip=request.client.host if request.client else "")

    return {"status": "logged_out"}


@router.get("/me")
async def get_current_user_info(request: Request) -> dict:
    """Get current authenticated user information."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {
        "username": user.username,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.value,
        "disabled": user.disabled,
    }


@router.get("/sessions")
async def list_sessions(request: Request) -> dict:
    """List active sessions (admin only)."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    user = get_user_from_token(token)
    if not user or not has_permission(user, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Admin access required")

    sessions = list_active_sessions()
    return {
        "count": len(sessions),
        "sessions": [
            {
                "session_id": s.session_id,
                "username": s.user.username,
                "role": s.user.role.value,
                "created_at": s.created_at.isoformat(),
                "expires_at": s.expires_at.isoformat(),
                "ip_address": s.ip_address,
            }
            for s in sessions
        ],
    }
