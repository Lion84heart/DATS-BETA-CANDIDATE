"""Audit API router."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from api.auth import UserRole, get_user_from_token, has_permission, get_audit_history

router = APIRouter(prefix="/audit", tags=["audit"])


def _get_user(request: Request):
    """Get authenticated user from request."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user_from_token(auth_header[7:])
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user


@router.get("/history")
async def get_audit(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    user: str | None = None,
    action: str | None = None,
) -> dict:
    """Get audit history."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.ANALYST):
            raise HTTPException(status_code=403, detail="Analyst access required")

        history = get_audit_history(limit=limit, offset=offset, user_filter=user, action_filter=action)
        return {
            "count": len(history),
            "limit": limit,
            "offset": offset,
            "entries": history,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_audit_summary(request: Request) -> dict:
    """Get audit summary statistics."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.ANALYST):
            raise HTTPException(status_code=403, detail="Analyst access required")

        history = get_audit_history(limit=10000)
        actions = {}
        users = {}
        for entry in history:
            actions[entry["action"]] = actions.get(entry["action"], 0) + 1
            users[entry["user"]] = users.get(entry["user"], 0) + 1

        return {
            "total_entries": len(history),
            "unique_actions": len(actions),
            "unique_users": len(users),
            "action_breakdown": actions,
            "user_breakdown": users,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_audit(request: Request, format: str = "json") -> dict:
    """Export audit history."""
    try:
        current_user = _get_user(request)
        if not has_permission(current_user, UserRole.ANALYST):
            raise HTTPException(status_code=403, detail="Analyst access required")

        history = get_audit_history(limit=10000)

        if format.lower() == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["timestamp", "user", "action", "resource", "details", "ip_address"])
            for entry in history:
                writer.writerow([
                    entry.get("timestamp", ""),
                    entry.get("user", ""),
                    entry.get("action", ""),
                    entry.get("resource", ""),
                    entry.get("details", ""),
                    entry.get("ip_address", ""),
                ])
            return {
                "format": "csv",
                "count": len(history),
                "csv_data": output.getvalue(),
            }

        return {
            "format": "json",
            "count": len(history),
            "entries": history,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
