"""Audit trail logging for security-sensitive operations.

Records all significant actions with immutable timestamps,
actor identification, and before/after states.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class AuditAction(Enum):
    """Categories of auditable actions."""

    ORDER_CREATED = auto()
    ORDER_CANCELLED = auto()
    ORDER_EXECUTED = auto()
    STRATEGY_CHANGED = auto()
    RISK_LIMIT_CHANGED = auto()
    KILL_SWITCH_TRIGGERED = auto()
    KILL_SWITCH_RESET = auto()
    LOGIN = auto()
    LOGOUT = auto()
    CONFIG_CHANGED = auto()
    API_KEY_CREATED = auto()
    API_KEY_REVOKED = auto()
    DATA_EXPORT = auto()
    SYSTEM_START = auto()
    SYSTEM_STOP = auto()


@dataclass(frozen=True)
class AuditEvent:
    """A single audit trail entry."""

    timestamp: float
    action: AuditAction
    actor: str
    resource: str
    details: dict[str, Any] = field(default_factory=dict)
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    session_id: str | None = None
    ip_address: str | None = None
    correlation_id: str | None = None

    @property
    def hash(self) -> str:
        """Cryptographic hash of the event for tamper detection."""
        data = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "timestamp_iso": _format_timestamp(self.timestamp),
            "action": self.action.name,
            "actor": self.actor,
            "resource": self.resource,
            "details": self.details,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "correlation_id": self.correlation_id,
            "hash": self.hash,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Immutable audit trail for security-sensitive operations.

    Stores events in memory with optional file persistence.
    All events are cryptographically hashed for integrity.
    """

    def __init__(self, persist_path: str | Path | None = None):
        """Initialize audit logger.

        Args:
            persist_path: Optional file path for event persistence.
        """
        self._events: list[AuditEvent] = []
        self._persist_path = Path(persist_path) if persist_path else None
        self._chain_hash: str = "0" * 64  # Genesis hash

    def log(
        self,
        action: AuditAction,
        actor: str,
        resource: str,
        details: dict[str, Any] | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        session_id: str | None = None,
        ip_address: str | None = None,
        correlation_id: str | None = None,
    ) -> AuditEvent:
        """Record an audit event.

        Args:
            action: Type of action.
            actor: Who performed the action.
            resource: What was affected.
            details: Additional context.
            before_state: State before action.
            after_state: State after action.
            session_id: Session identifier.
            ip_address: Client IP.
            correlation_id: Request correlation ID.

        Returns:
            The created AuditEvent.
        """
        event = AuditEvent(
            timestamp=time.time(),
            action=action,
            actor=actor,
            resource=resource,
            details=details or {},
            before_state=before_state,
            after_state=after_state,
            session_id=session_id,
            ip_address=ip_address,
            correlation_id=correlation_id,
        )

        # Chain hash: previous hash + current hash -> new chain
        self._chain_hash = hashlib.sha256(
            f"{self._chain_hash}{event.hash}".encode("utf-8")
        ).hexdigest()

        self._events.append(event)

        if self._persist_path:
            self._append_to_file(event)

        return event

    def get_events(
        self,
        action: AuditAction | None = None,
        actor: str | None = None,
        since: float | None = None,
        limit: int = 1000,
    ) -> list[AuditEvent]:
        """Query audit events with filtering.

        Args:
            action: Filter by action type.
            actor: Filter by actor.
            since: Minimum timestamp.
            limit: Maximum results.

        Returns:
            Matching events, newest first.
        """
        events = reversed(self._events)
        if action:
            events = (e for e in events if e.action == action)
        if actor:
            events = (e for e in events if e.actor == actor)
        if since:
            events = (e for e in events if e.timestamp >= since)
        return list(events)[:limit]

    def verify_integrity(self) -> tuple[bool, int]:
        """Verify the integrity of the audit chain.

        Returns:
            (is_valid, event_count)
        """
        chain = "0" * 64
        for event in self._events:
            expected = hashlib.sha256(
                f"{chain}{event.hash}".encode("utf-8")
            ).hexdigest()
            chain = expected
        return chain == self._chain_hash, len(self._events)

    def export(self, path: str | Path) -> None:
        """Export all events to a JSON file.

        Args:
            path: Output file path.
        """
        data = {
            "events": [e.to_dict() for e in self._events],
            "chain_hash": self._chain_hash,
            "count": len(self._events),
        }
        Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def _append_to_file(self, event: AuditEvent) -> None:
        """Append single event to persistence file."""
        if not self._persist_path:
            return
        try:
            with open(self._persist_path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except OSError:
            pass  # Persistence failure shouldn't block logging

    @property
    def event_count(self) -> int:
        """Total number of events logged."""
        return len(self._events)

    @property
    def chain_hash(self) -> str:
        """Current chain hash for tamper detection."""
        return self._chain_hash


def _format_timestamp(ts: float) -> str:
    """Format timestamp as ISO 8601 string."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
