from __future__ import annotations

from datetime import date

from .adapters import DemoCalendar
from .agents import ProductivityAgent
from .models import ActionKind, ProposedAction
from .storage import SQLiteStore


def resolve_approval(store: SQLiteStore, approval_id: str, decision: str,
                     edited_title: str | None = None,
                     edited_due_date: str | None = None,
                     feedback: str | None = None) -> dict[str, object]:
    approval = store.get_approval(approval_id)
    if not approval or approval["status"] != "pending":
        raise ValueError("approval does not exist or has already been resolved")
    normalized = decision.strip().lower()
    if normalized not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")
    if normalized == "reject":
        resolution = {"decision": "reject", "feedback": feedback}
        store.resolve_approval(approval_id, "rejected", resolution)
        store.add_feedback_example(approval_id, approval["action"], "ignore", feedback)
        store.record("approval_rejected", {"approval_id": approval_id, **resolution})
        return {"approval_id": approval_id, "status": "rejected", "feedback": feedback}

    raw_action = approval["action"]
    if not isinstance(raw_action, dict):
        raise ValueError("stored approval action is invalid")
    payload = dict(raw_action.get("payload") or {})
    if edited_due_date is not None:
        payload["due_date"] = date.fromisoformat(edited_due_date) if edited_due_date else None
    elif payload.get("due_date"):
        payload["due_date"] = date.fromisoformat(str(payload["due_date"]))
    action = ProposedAction(
        kind=ActionKind(str(raw_action["kind"])),
        title=edited_title or str(raw_action["title"]),
        confidence=float(raw_action["confidence"]),
        rationale=str(raw_action["rationale"]),
        payload=payload,
    )
    if action.kind not in {ActionKind.CREATE_TASK, ActionKind.UPDATE_TASK}:
        raise ValueError(f"approval execution is not implemented for {action.kind.value}")
    task = ProductivityAgent(store, DemoCalendar()).execute(action)
    resolution = {
        "decision": "approve", "task_id": task.id,
        "edited": edited_title is not None or edited_due_date is not None,
        "feedback": feedback,
    }
    store.resolve_approval(approval_id, "approved", resolution)
    feedback_action = dict(raw_action)
    feedback_action["title"] = action.title
    store.add_feedback_example(approval_id, feedback_action, "task", feedback)
    store.record("approval_approved", {"approval_id": approval_id, **resolution})
    task_value: dict[str, object] = {
        "id": task.id, "title": task.title,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "status": task.status, "source_url": task.source_url,
    }
    return {"approval_id": approval_id, "status": "approved", "task": task_value}
