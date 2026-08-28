"""Authentication and authorization for DATS Platform API.

Provides JWT-based authentication with role-based access control.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

try:
    from fastapi import HTTPException, status
except ImportError:
    HTTPException = None  # type: ignore[misc,assignment]
    status = None  # type: ignore[misc,assignment]

# Use python-jose for JWT if available, otherwise fallback to a simple token
# For production readiness we implement a proper JWT scheme
try:
    from jose import JWTError, jwt
    HAS_JOSE = True
except ImportError:
    HAS_JOSE = False


class UserRole(Enum):
    """RBAC roles for platform operators."""

    VIEWER = "viewer"      # Read-only access
    ANALYST = "analyst"    # Can review decisions, export packages
    OPERATOR = "operator"  # Can start/stop trading, manage orders
    ADMIN = "admin"        # Full access including config, user management


@dataclass(frozen=True, slots=True)
class User:
    """Authenticated user."""

    username: str
    role: UserRole
    email: str = ""
    full_name: str = ""
    disabled: bool = False


@dataclass
class Session:
    """Active user session."""

    session_id: str
    user: User
    created_at: datetime
    expires_at: datetime
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ip_address: str = ""
    user_agent: str = ""


def _hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256.

    Format: pbkdf2$<iterations>$<salt_hex>$<hash_hex>
    OWASP-recommended 600,000 iterations for HMAC-SHA256.
    """
    import hashlib
    iterations = 600_000
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2${iterations}${salt.hex()}${dk.hex()}"


# In-memory user store (replace with database in production)
_USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "username": "admin",
        "full_name": "System Administrator",
        "email": "admin@dats.local",
        "role": UserRole.ADMIN,
        "password_hash": _hash_password("admin"),
        "disabled": False,
    },
    "operator": {
        "username": "operator",
        "full_name": "Trading Operator",
        "email": "operator@dats.local",
        "role": UserRole.OPERATOR,
        "password_hash": _hash_password("operator"),
        "disabled": False,
    },
    "analyst": {
        "username": "analyst",
        "full_name": "Decision Analyst",
        "email": "analyst@dats.local",
        "role": UserRole.ANALYST,
        "password_hash": _hash_password("analyst"),
        "disabled": False,
    },
    "viewer": {
        "username": "viewer",
        "full_name": "Read-Only Viewer",
        "email": "viewer@dats.local",
        "role": UserRole.VIEWER,
        "password_hash": _hash_password("viewer"),
        "disabled": False,
    },
}

# In-memory session store
_SESSIONS: dict[str, Session] = {}

import os

# JWT configuration — read from environment or generate securely per process
_SECRET_KEY = os.environ.get(
    "SECURITY_JWT_SECRET",
    secrets.token_urlsafe(32),
)
_ALGORITHM = os.environ.get("SECURITY_ALGORITHM", "HS256")
_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("SECURITY_TOKEN_EXPIRY_MINUTES", "30"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its stored hash (constant-time)."""
    import hashlib
    import hmac
    try:
        scheme, iterations_s, salt_hex, hash_hex = hashed_password.split("$")
        if scheme != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode(), bytes.fromhex(salt_hex), int(iterations_s)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def authenticate_user(username: str, password: str) -> User | None:
    """Authenticate a user by username and password."""
    user_data = _USERS.get(username)
    if not user_data:
        return None
    if user_data.get("disabled", False):
        return None
    stored = user_data.get("password_hash", "")
    if not verify_password(password, stored):
        return None
    return User(
        username=user_data["username"],
        role=user_data["role"],
        email=user_data.get("email", ""),
        full_name=user_data.get("full_name", ""),
        disabled=user_data.get("disabled", False),
    )


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token for a user."""
    if not HAS_JOSE:
        # Fallback: simple token with user info
        expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES))
        return f"{user.username}:{user.role.value}:{int(expire.timestamp())}"

    to_encode = {
        "sub": user.username,
        "role": user.role.value,
        "email": user.email,
        "name": user.full_name,
    }
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, _SECRET_KEY, algorithm=_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode a JWT access token."""
    if not HAS_JOSE:
        # Fallback: parse simple token
        parts = token.split(":")
        if len(parts) != 3:
            return None
        try:
            expire_ts = int(parts[2])
            if datetime.now(timezone.utc).timestamp() > expire_ts:
                return None
            return {
                "sub": parts[0],
                "role": parts[1],
                "exp": expire_ts,
            }
        except ValueError:
            return None

    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        return payload
    except JWTError:
        return None


def get_user_from_token(token: str) -> User | None:
    """Get a User from an access token."""
    payload = decode_token(token)
    if payload is None:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user_data = _USERS.get(username)
    if not user_data:
        return None
    return User(
        username=user_data["username"],
        role=user_data["role"],
        email=user_data.get("email", ""),
        full_name=user_data.get("full_name", ""),
        disabled=user_data.get("disabled", False),
    )


def create_session(user: User, ip_address: str = "", user_agent: str = "") -> Session:
    """Create a new session for a user."""
    session_id = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    session = Session(
        session_id=session_id,
        user=user,
        created_at=now,
        expires_at=now + timedelta(minutes=_ACCESS_TOKEN_EXPIRE_MINUTES),
        last_activity=now,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    _SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Get a session by ID."""
    session = _SESSIONS.get(session_id)
    if session is None:
        return None
    if session.expires_at < datetime.now(timezone.utc):
        del _SESSIONS[session_id]
        return None
    return session


def end_session(session_id: str) -> bool:
    """End a session."""
    if session_id in _SESSIONS:
        del _SESSIONS[session_id]
        return True
    return False


def list_active_sessions() -> list[Session]:
    """List all active sessions."""
    now = datetime.now(timezone.utc)
    active = []
    for sid, session in list(_SESSIONS.items()):
        if session.expires_at < now:
            del _SESSIONS[sid]
        else:
            active.append(session)
    return active


def has_permission(user: User, required_role: UserRole) -> bool:
    """Check if a user has at least the required role."""
    role_hierarchy = {
        UserRole.VIEWER: 0,
        UserRole.ANALYST: 1,
        UserRole.OPERATOR: 2,
        UserRole.ADMIN: 3,
    }
    return role_hierarchy.get(user.role, 0) >= role_hierarchy.get(required_role, 0)


def get_current_user(request) -> User:
    """Extract and validate the current user from request headers.

    Raises:
        HTTPException: 401 if not authenticated or token invalid.
    """
    from fastapi import HTTPException, status
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = get_user_from_token(auth_header[7:])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    if user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account disabled")
    return user


def require_role(required_role: UserRole):
    """Create a dependency that requires at least the specified role."""
    def _check_role(request) -> User:
        user = get_current_user(request)
        if not has_permission(user, required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{required_role.value} access required",
            )
        return user
    return _check_role


# Audit history store
_AUDIT_HISTORY: list[dict[str, Any]] = []


def record_audit(user: User | None, action: str, resource: str, details: str = "", ip: str = "") -> None:
    """Record an audit entry."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user.username if user else "anonymous",
        "role": user.role.value if user else "none",
        "action": action,
        "resource": resource,
        "details": details,
        "ip_address": ip,
    }
    _AUDIT_HISTORY.append(entry)


def get_audit_history(limit: int = 100, offset: int = 0, user_filter: str | None = None, action_filter: str | None = None) -> list[dict[str, Any]]:
    """Get audit history with optional filtering."""
    results = _AUDIT_HISTORY
    if user_filter:
        results = [e for e in results if e["user"] == user_filter]
    if action_filter:
        results = [e for e in results if e["action"] == action_filter]
    return results[-(offset + limit):-offset if offset else None][::-1] if offset else results[-limit:][::-1]
