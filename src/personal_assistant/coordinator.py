from __future__ import annotations

from datetime import date

from .agents import DiscoveryAgent, PersonalizationAgent, ProductivityAgent
from .models import ActionDecision, ActionKind, WorkflowResult
from .policy import SafetyPolicy
from .ports import AuditPort, InboxPort


class CoordinatorAgent:
    """Routes triggers, applies safety policy, executes approved low-risk actions, and audits results."""

    def __init__(self, inbox: InboxPort, productivity: ProductivityAgent,
                 personalization: PersonalizationAgent, discovery: DiscoveryAgent,
                 audit: AuditPort, policy: SafetyPolicy | None = None) -> None:
        self.inbox = inbox
        self.productivity = productivity
        self.personalization = personalization
        self.discovery = discovery
        self.audit = audit
        self.policy = policy or SafetyPolicy()

    def monitor_inbox(self, max_items: int | None = None) -> list[WorkflowResult]:
        results = []
        for email in self.inbox.unread_primary():
            if self.audit.was_processed("gmail", email.id):
                continue
            if max_items is not None and len(results) >= max_items:
                break
            thread = self.inbox.thread(email.thread_id)
            summary, action = self.productivity.process_email(email, thread)
            action.decision = self.policy.decide(action)
            observations = [f"Retrieved {len(thread)} message(s) from the email thread."]
            if action.decision is ActionDecision.EXECUTE and action.kind in {
                ActionKind.CREATE_TASK, ActionKind.UPDATE_TASK
            }:
                task = self.productivity.execute(action)
                observations.append(f"Saved tentative task {task.id}.")
            elif action.decision is ActionDecision.PROPOSE:
                approval_id = self.audit.queue_approval(email.id, action.to_dict())
                action.payload["approval_id"] = approval_id
                observations.append(f"Queued for human confirmation as {approval_id}.")
            else:
                observations.append("No external action taken.")
            result = WorkflowResult(email.id, summary, [action], observations)
            self.audit.record("inbox_workflow", result.to_dict())
            self.audit.mark_processed("gmail", email.id)
            results.append(result)
        return results

    def find_activities(self, request: str, start: date, end: date) -> WorkflowResult:
        memories = self.personalization.context_for(request)
        action = self.discovery.recommend_activities(memories, start, end)
        if hasattr(self.audit, "rank_content"):
            action.payload["candidates"] = self.audit.rank_content(
                "activity", action.payload["candidates"]
            )
        action.decision = self.policy.decide(action)
        result = WorkflowResult(
            trigger="activity_request",
            summary=f"Found {len(action.payload['candidates'])} available candidate(s).",
            actions=[action],
            observations=[f"Retrieved {len(memories)} relevant long-term memories."],
        )
        self.audit.record("activity_workflow", result.to_dict())
        return result

    def daily_news(self, request: str = "my confirmed news interests") -> WorkflowResult:
        memories = self.personalization.context_for(request)
        action = self.discovery.summarize_news(memories)
        if hasattr(self.audit, "rank_content"):
            action.payload["stories"] = self.audit.rank_content("news", action.payload["stories"])
        action.decision = self.policy.decide(action)
        result = WorkflowResult(
            trigger="daily_news",
            summary=f"Selected {len(action.payload['stories'])} current stories.",
            actions=[action],
            observations=[f"Retrieved {len(memories)} relevant news preferences."],
        )
        self.audit.record("news_workflow", result.to_dict())
        return result
