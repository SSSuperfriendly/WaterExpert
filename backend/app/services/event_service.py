"""Alert/event handling with a closed loop (review item 27).

The review found alerts could be *displayed* but never acted on: there was no
record of who saw a high-risk day, whether it was real, what was done, or
whether it was closed. An :class:`EventService` gives every alert a state
machine (发现 → 分派 → 确认 → 处置 → 复核 → 关闭), a per-transition history, a
false-positive escape hatch, escalation, and a close-with-post-mortem step, plus
a notification adapter so a transition can push to a webhook.

The loop is "closed" because an event cannot be silently dropped: every exit is
either ``closed`` (with a post-mortem) or ``false_positive`` (with a reason).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.app.config import Settings
from backend.app.domain.codes import ErrorCode, EventStatus, Severity
from backend.app.services.state_store import EVENTS_TABLE, SqliteStateStore
from backend.app.services.upload_guard import UploadRejected

logger = logging.getLogger(__name__)

ID_LENGTH = 12

#: Which event states may follow which (review item 27).
EVENT_TRANSITIONS: dict[str, set[str]] = {
    EventStatus.OPEN: {EventStatus.ASSIGNED, EventStatus.FALSE_POSITIVE},
    EventStatus.ASSIGNED: {EventStatus.ACKNOWLEDGED, EventStatus.FALSE_POSITIVE},
    EventStatus.ACKNOWLEDGED: {EventStatus.HANDLING, EventStatus.FALSE_POSITIVE},
    EventStatus.HANDLING: {EventStatus.REVIEWING, EventStatus.CLOSED, EventStatus.FALSE_POSITIVE},
    EventStatus.REVIEWING: {EventStatus.CLOSED, EventStatus.HANDLING, EventStatus.FALSE_POSITIVE},
    EventStatus.CLOSED: set(),
    EventStatus.FALSE_POSITIVE: set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class EventNotFound(KeyError):
    """No event with that id."""


class EventService:
    def __init__(self, settings: Settings, store: SqliteStateStore) -> None:
        self.settings = settings
        self.store = store

    # -- creation ------------------------------------------------------------

    def create(
        self,
        *,
        title: str,
        description: str,
        severity: str,
        case_id: str | None = None,
        target_date: str | None = None,
        source: str = "manual",
        creator: str | None = None,
    ) -> dict[str, Any]:
        severity = severity if severity in {str(s) for s in Severity} else str(Severity.MEDIUM)
        timestamp = utc_now()
        record = {
            "event_id": uuid4().hex[:ID_LENGTH],
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": str(EventStatus.OPEN),
            "severity": severity,
            "title": title.strip(),
            "description": description,
            "case_id": case_id,
            "target_date": target_date,
            "source": source,
            "assignee": None,
            "creator": creator,
            "history": [{"status": str(EventStatus.OPEN), "at": timestamp, "by": creator, "note": "opened"}],
            "escalated": False,
            "post_mortem": None,
        }
        created = self.store.insert(EVENTS_TABLE, record)
        self._notify(created, "created")
        return created

    # -- reads ---------------------------------------------------------------

    def get(self, event_id: str) -> dict[str, Any]:
        event = self.store.get(EVENTS_TABLE, event_id)
        if event is None:
            raise EventNotFound(event_id)
        return event

    def list(
        self,
        *,
        status: str | None = None,
        severity: str | None = None,
        case_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status
        if severity:
            filters["severity"] = severity
        if case_id:
            filters["case_id"] = case_id
        return self.store.list(EVENTS_TABLE, filters=filters or None, limit=limit)

    # -- transitions ---------------------------------------------------------

    def transition(
        self,
        event_id: str,
        to_stage: str,
        *,
        actor: str,
        note: str | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        event = self.get(event_id)
        current = str(event.get("status", EventStatus.OPEN))
        if to_stage not in EVENT_TRANSITIONS.get(current, set()):
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                f"Cannot move event from {current} to {to_stage}.",
            )
        timestamp = utc_now()
        updates: dict[str, Any] = {
            "status": to_stage,
            "updated_at": timestamp,
            "history": [
                *(event.get("history") or []),
                {"status": to_stage, "at": timestamp, "by": actor, "note": note},
            ],
        }
        if assignee:
            updates["assignee"] = assignee
        if to_stage == str(EventStatus.ACKNOWLEDGED):
            updates["acknowledged_at"] = timestamp
        elif to_stage == str(EventStatus.CLOSED):
            updates["closed_at"] = timestamp
        elif to_stage == str(EventStatus.ASSIGNED) and assignee:
            updates["assigned_at"] = timestamp

        updated = self.store.update(EVENTS_TABLE, event_id, updates)
        self._notify(updated, to_stage)
        return updated

    def close(self, event_id: str, actor: str, post_mortem: str, note: str | None = None) -> dict[str, Any]:
        """Close with a mandatory post-mortem (review item 27's 复盘 step)."""
        event = self.get(event_id)
        current = str(event.get("status", EventStatus.OPEN))
        if current not in {str(EventStatus.HANDLING), str(EventStatus.REVIEWING)}:
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                "An event may only be closed from handling or reviewing.",
            )
        timestamp = utc_now()
        updated = self.store.update(
            EVENTS_TABLE,
            event_id,
            {
                "status": str(EventStatus.CLOSED),
                "closed_at": timestamp,
                "post_mortem": post_mortem.strip(),
                "updated_at": timestamp,
                "history": [
                    *(event.get("history") or []),
                    {"status": str(EventStatus.CLOSED), "at": timestamp, "by": actor, "note": note},
                ],
            },
        )
        self._notify(updated, str(EventStatus.CLOSED))
        return updated

    def mark_false_positive(self, event_id: str, actor: str, reason: str) -> dict[str, Any]:
        """Exit the loop via the false-positive hatch, with a required reason."""
        event = self.get(event_id)
        if str(event.get("status")) in {
            str(EventStatus.CLOSED),
            str(EventStatus.FALSE_POSITIVE),
        }:
            raise UploadRejected(
                ErrorCode.INVALID_STATE_TRANSITION,
                "A closed or already-resolved event cannot be re-resolved.",
            )
        timestamp = utc_now()
        updated = self.store.update(
            EVENTS_TABLE,
            event_id,
            {
                "status": str(EventStatus.FALSE_POSITIVE),
                "post_mortem": reason.strip(),
                "updated_at": timestamp,
                "history": [
                    *(event.get("history") or []),
                    {
                        "status": str(EventStatus.FALSE_POSITIVE),
                        "at": timestamp,
                        "by": actor,
                        "note": reason,
                    },
                ],
            },
        )
        self._notify(updated, str(EventStatus.FALSE_POSITIVE))
        return updated

    def escalate(self, event_id: str, actor: str, note: str | None = None) -> dict[str, Any]:
        """Raise the severity of an unhandled event and flag it."""
        event = self.get(event_id)
        order = [str(Severity.LOW), str(Severity.MEDIUM), str(Severity.HIGH), str(Severity.CRITICAL)]
        current = str(event.get("severity", Severity.MEDIUM))
        next_severity = order[min(order.index(current) + 1, len(order) - 1)]
        updated = self.store.update(
            EVENTS_TABLE,
            event_id,
            {
                "severity": next_severity,
                "escalated": True,
                "updated_at": utc_now(),
                "history": [
                    *(event.get("history") or []),
                    {"status": "escalated", "at": utc_now(), "by": actor, "note": note},
                ],
            },
        )
        self._notify(updated, "escalated")
        return updated

    # -- notifications -------------------------------------------------------

    def _notify(self, event: dict[str, Any], transition: str) -> None:
        """Push a notification: console always, webhook when configured."""
        payload = {
            "event": "event_transition",
            "event_id": event.get("event_id"),
            "title": event.get("title"),
            "severity": event.get("severity"),
            "status": event.get("status"),
            "transition": transition,
        }
        logger.info("event %s -> %s", event.get("event_id"), transition)
        webhook = self.settings.notification_webhook_url
        if not webhook:
            return
        try:
            request = urllib.request.Request(
                webhook,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(request, timeout=3)  # noqa: S310 — config-supplied URL
        except Exception as exc:  # noqa: BLE001 — notifications must never break the request
            logger.warning("event webhook failed: %s", exc)

    def summary(self) -> dict[str, Any]:
        events = self.store.list(EVENTS_TABLE)
        by_status: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for event in events:
            status = str(event.get("status", EventStatus.OPEN))
            by_status[status] = by_status.get(status, 0) + 1
            severity = str(event.get("severity", Severity.MEDIUM))
            by_severity[severity] = by_severity.get(severity, 0) + 1
        open_count = sum(
            v for k, v in by_status.items() if k not in {str(EventStatus.CLOSED), str(EventStatus.FALSE_POSITIVE)}
        )
        return {
            "total": len(events),
            "open": open_count,
            "by_status": by_status,
            "by_severity": by_severity,
        }
