from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class ActionDecision(str, Enum):
    EXECUTE = "execute"
    PROPOSE = "propose"
    IGNORE = "ignore"


class ActionKind(str, Enum):
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    CREATE_EVENT = "create_event"
    RECOMMEND = "recommend"
    STORE_MEMORY = "store_memory"
    NONE = "none"


@dataclass(slots=True)
class Email:
    id: str
    thread_id: str
    sender: str
    subject: str
    body: str
    received_at: datetime
    web_url: str


@dataclass(slots=True)
class Task:
    id: str
    title: str
    due_date: date | None = None
    source_url: str | None = None
    source_id: str | None = None
    status: str = "tentative"
    notes: str = ""


@dataclass(slots=True)
class Memory:
    id: str
    text: str
    category: str
    confidence: float
    confirmed: bool
    source: str
    created_at: datetime


@dataclass(slots=True)
class ProposedAction:
    kind: ActionKind
    title: str
    confidence: float
    rationale: str
    payload: dict[str, Any] = field(default_factory=dict)
    decision: ActionDecision | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.value
        result["decision"] = self.decision.value if self.decision else None
        return result


@dataclass(slots=True)
class WorkflowResult:
    trigger: str
    summary: str
    actions: list[ProposedAction]
    observations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "summary": self.summary,
            "actions": [action.to_dict() for action in self.actions],
            "observations": self.observations,
        }

