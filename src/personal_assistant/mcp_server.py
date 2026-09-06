from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from .adapters import DemoCalendar, DemoInbox, DemoSearch
from .approval_service import resolve_approval
from .agents import DiscoveryAgent, PersonalizationAgent, ProductivityAgent
from .activities import SeattleActivitySearch
from .calendar import GoogleCalendar
from .coordinator import CoordinatorAgent
from .embeddings import OllamaEmbeddingProvider
from .gmail import GmailInbox
from .models import Email, Memory, Task
from .news import PersonalizedNewsSearch
from .policy import SafetyPolicy
from .reasoning import OllamaEmailReasoner, OpenAIEmailReasoner
from .storage import SQLiteStore


mcp = FastMCP("personal-assistant")


def _store() -> SQLiteStore:
    embedder = None
    if os.getenv("ASSISTANT_MEMORY_MODE", "ollama") == "ollama":
        embedder = OllamaEmbeddingProvider(
            model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout=float(os.getenv("OLLAMA_EMBEDDING_TIMEOUT", "20")),
        )
    return SQLiteStore(os.getenv("ASSISTANT_DB_PATH", "assistant.db"), embedder=embedder)


def _inbox(source: str) -> DemoInbox | GmailInbox:
    if source == "gmail":
        return GmailInbox(
            os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"),
            os.getenv("GMAIL_TOKEN_PATH", "token.json"),
        )
    if source == "demo":
        now = datetime.now(timezone.utc)
        return DemoInbox([
            Email(
                id="mcp_demo_email", thread_id="mcp_demo_thread",
                sender="teacher@example.edu", subject="Return permission form",
                body="Please return the permission form by 2026-09-10.",
                received_at=now,
                web_url="https://mail.google.com/mail/u/0/#inbox/mcp_demo_email",
            )
        ])
    raise ValueError("source must be 'demo' or 'gmail'")


def _coordinator(source: str = "demo", reasoning_mode: str = "rules",
                 calendar_source: str = "demo") -> CoordinatorAgent:
    store = _store()
    if calendar_source not in {"demo", "google"}:
        raise ValueError("calendar_source must be 'demo' or 'google'")
    calendar = GoogleCalendar(
        os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        os.getenv("GMAIL_TOKEN_PATH", "token.json"),
    ) if calendar_source == "google" else DemoCalendar()
    if reasoning_mode not in {"rules", "ollama", "openai"}:
        raise ValueError("reasoning_mode must be 'rules', 'ollama', or 'openai'")
    reasoner = None
    if reasoning_mode == "openai":
        reasoner = OpenAIEmailReasoner(
            model=os.getenv("OPENAI_MODEL", ""), api_key=os.getenv("OPENAI_API_KEY")
        )
    elif reasoning_mode == "ollama":
        reasoner = OllamaEmailReasoner(
            model=os.getenv("OLLAMA_MODEL", "qwen3:4b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout=float(os.getenv("OLLAMA_EMAIL_TIMEOUT", "45")),
        )
    return CoordinatorAgent(
        inbox=_inbox(source),
        productivity=ProductivityAgent(store, calendar, reasoner, store),
        personalization=PersonalizationAgent(store),
        discovery=DiscoveryAgent(DemoSearch(), calendar),
        audit=store,
        policy=SafetyPolicy(
            auto_action_threshold=float(os.getenv("ASSISTANT_AUTO_ACTION_THRESHOLD", "0.85")),
            confirmation_threshold=float(os.getenv("ASSISTANT_CONFIRM_THRESHOLD", "0.55")),
        ),
    )


def _task_dict(task: Task) -> dict[str, Any]:
    value = asdict(task)
    value["due_date"] = task.due_date.isoformat() if task.due_date else None
    return value


def _memory_dict(memory: Memory) -> dict[str, Any]:
    value = asdict(memory)
    value["created_at"] = memory.created_at.isoformat()
    return value


@mcp.tool()
def gmail_process_primary_inbox(source: str = "demo",
                                reasoning_mode: str = "rules",
                                calendar_source: str = "demo",
                                max_items: int = 5) -> list[dict[str, Any]]:
    """Process new Primary inbox messages using demo or read-only Gmail access.

    High-confidence, low-risk items become tentative local tasks. Ambiguous actions
    are proposed for human confirmation. Already processed message IDs are skipped.
    """
    return [
        result.to_dict()
        for result in _coordinator(source, reasoning_mode, calendar_source).monitor_inbox(
            max(1, min(max_items, 10))
        )
    ]


@mcp.tool()
def tasks_list_open() -> list[dict[str, Any]]:
    """List open and tentative tasks from the assistant's operational store."""
    return [_task_dict(task) for task in _store().list_open()]


@mcp.tool()
def tasks_mark_complete(task_id: str) -> dict[str, Any]:
    """Mark one local task complete so it no longer appears in the open-task list."""
    store = _store()
    task = store.complete_task(task_id)
    store.record("task_completed", {"task_id": task.id, "title": task.title, "source": "mcp"})
    return {"completed": True, "task": _task_dict(task)}


@mcp.tool()
def tasks_reopen(task_id: str) -> dict[str, Any]:
    """Reopen a completed local task and return it to the open-task list."""
    store = _store()
    task = store.reopen_task(task_id)
    store.record("task_reopened", {"task_id": task.id, "title": task.title, "source": "mcp"})
    return {"reopened": True, "task": _task_dict(task)}


@mcp.tool()
def tasks_create_tentative(title: str, due_date: str | None = None,
                           source_url: str | None = None, source_id: str | None = None) -> dict[str, Any]:
    """Create a reversible tentative task; dates must use YYYY-MM-DD format."""
    parsed_due = date.fromisoformat(due_date) if due_date else None
    store = _store()
    task = Task(
        id=store.new_id("task"), title=title, due_date=parsed_due,
        source_url=source_url, source_id=source_id, status="tentative",
        notes="Created through MCP tool.",
    )
    store.create(task)
    store.record("mcp_task_created", _task_dict(task))
    return _task_dict(task)


@mcp.tool()
def approvals_list_pending() -> list[dict[str, object]]:
    """List uncertain actions waiting for a human decision."""
    return _store().pending_approvals()


@mcp.tool()
def approvals_resolve(approval_id: str, decision: str,
                      edited_title: str | None = None,
                      edited_due_date: str | None = None,
                      feedback: str | None = None) -> dict[str, object]:
    """Approve, edit-and-approve, or reject one pending action.

    The decision must be 'approve' or 'reject'. Edited values are applied only
    when approving. This explicit tool call represents the human decision.
    """
    return resolve_approval(
        _store(), approval_id, decision, edited_title, edited_due_date, feedback
    )


@mcp.tool()
def memory_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve relevant confirmed personal preferences and interests."""
    bounded_limit = max(1, min(limit, 10))
    return [_memory_dict(memory) for memory in _store().search(query, bounded_limit)]


@mcp.tool()
def memory_store_confirmed(text: str, category: str, source: str,
                           user_confirmed: bool = False) -> dict[str, Any]:
    """Store durable personal context only after explicit user confirmation."""
    if not user_confirmed:
        return {"stored": False, "reason": "Explicit user confirmation is required."}
    store = _store()
    memory = Memory(
        id=store.new_id("memory"), text=text, category=category, confidence=1.0,
        confirmed=True, source=source, created_at=datetime.now(timezone.utc),
    )
    store.add(memory)
    store.record("mcp_memory_stored", _memory_dict(memory))
    return {"stored": True, "memory": _memory_dict(memory)}


@mcp.tool()
def activities_recommend(request: str, start_date: str | None = None,
                         days_ahead: int = 60) -> dict[str, Any]:
    """Recommend live Seattle activities using preferences and calendar availability."""
    start = date.fromisoformat(start_date) if start_date else date.today()
    bounded_days = max(1, min(days_ahead, 90))
    coordinator = _coordinator()
    calendar = GoogleCalendar(
        os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        os.getenv("GMAIL_TOKEN_PATH", "token.json"),
    ) if os.getenv("ASSISTANT_CALENDAR_SOURCE", "demo") == "google" else DemoCalendar()
    coordinator.discovery = DiscoveryAgent(SeattleActivitySearch(), calendar)
    return coordinator.find_activities(request, start, start + timedelta(days=bounded_days)).to_dict()


@mcp.tool()
def news_daily_summary() -> dict[str, Any]:
    """Create a current, link-grounded digest from confirmed news preferences."""
    coordinator = _coordinator()
    coordinator.discovery = DiscoveryAgent(PersonalizedNewsSearch(), DemoCalendar())
    return coordinator.daily_news(
        "news interests arts culture technology AI cats Seattle uplifting food"
    ).to_dict()


@mcp.resource("tasks://open")
def open_tasks_resource() -> str:
    """Read-only snapshot of open and tentative tasks."""
    return json.dumps([_task_dict(task) for task in _store().list_open()], indent=2)


@mcp.resource("profile://preferences")
def preferences_resource() -> str:
    """Read-only snapshot of stored personal memories."""
    return json.dumps([_memory_dict(memory) for memory in _store().list_memories()], indent=2)


@mcp.resource("audit://recent")
def audit_resource() -> str:
    """Read-only recent workflow and tool audit events."""
    return json.dumps(_store().recent_audit(), indent=2)


@mcp.resource("approvals://pending")
def pending_approvals_resource() -> str:
    """Read-only snapshot of actions awaiting human confirmation."""
    return json.dumps(_store().pending_approvals(), indent=2)


@mcp.prompt()
def review_inbox(source: str = "demo") -> str:
    """Reusable workflow prompt for safely processing an inbox."""
    return (
        f"Process the {source} Primary inbox using gmail_process_primary_inbox. "
        "Report created tentative tasks, ignored messages, and all actions awaiting confirmation. "
        "Do not claim that a proposed action was executed."
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
