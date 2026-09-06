from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

from .models import ActionKind, Email, Memory, ProposedAction, Task
from .ports import CalendarPort, FeedbackPort, MemoryPort, SearchPort, TaskPort
from .reasoning import EmailReasoner
from .storage import SQLiteStore


class ProductivityAgent:
    """Understands inbox items and reconciles them with operational state."""

    ACTION_TERMS = ("please", "can you", "could you", "need to", "remember to", "due", "submit")
    CALENDAR_REMINDER_TERMS = ("appointment", "reservation")
    CALENDAR_STOP_WORDS = {
        "appointment", "reservation", "reminder", "confirmation", "confirmed", "upcoming",
        "your", "the", "for", "with", "at", "on", "re", "fwd", "calendar", "event",
    }

    def __init__(self, tasks: TaskPort, calendar: CalendarPort,
                 reasoner: EmailReasoner | None = None,
                 feedback: FeedbackPort | None = None) -> None:
        self.tasks = tasks
        self.calendar = calendar
        self.reasoner = reasoner
        self.feedback = feedback

    def process_email(self, email: Email, thread: list[Email]) -> tuple[str, ProposedAction]:
        calendar_action = self._calendar_reminder_action(email, thread)
        if calendar_action is not None:
            return self._summary(email), calendar_action
        if self.reasoner is not None:
            try:
                return self._process_with_reasoner(email, thread)
            except RuntimeError:
                summary, action = self._process_with_rules(email, thread)
                action.confidence = min(action.confidence, 0.8)
                action.rationale += " Local model analysis timed out, so conservative rules were used."
                action.payload["analysis_source"] = "rules_fallback"
                return summary, action
        return self._process_with_rules(email, thread)

    def _calendar_reminder_action(self, email: Email,
                                  thread: list[Email]) -> ProposedAction | None:
        text = f"{email.subject}. {email.body}".strip()
        if not any(term in text.lower() for term in self.CALENDAR_REMINDER_TERMS):
            return None
        event_date, explicit = self._extract_due_date(text, email.received_at.date())
        title = self._calendar_task_title(email, event_date)
        payload = {
            "due_date": event_date, "event_date": event_date,
            "source_url": email.web_url, "source_id": email.id,
            "thread_messages": len(thread), "analysis_source": "calendar_reminder_rule",
            "email_subject": email.subject, "email_sender": email.sender,
        }
        if event_date is None:
            return ProposedAction(
                kind=ActionKind.CREATE_TASK, title=title, confidence=0.7,
                rationale=("This appears to be an appointment or reservation reminder, but its "
                           "date could not be determined, so calendar presence requires review."),
                payload=payload,
            )
        try:
            calendar_items = self.calendar.conflicts_on(event_date)
        except (RuntimeError, ValueError):
            return ProposedAction(
                kind=ActionKind.CREATE_TASK, title=title, confidence=0.7,
                rationale=(f"This reminder is for {event_date.isoformat()}, but the calendar could "
                           "not be checked, so the task requires review."),
                payload=payload,
            )
        if self._matching_calendar_item(text, calendar_items):
            return ProposedAction(
                kind=ActionKind.NONE, title=email.subject, confidence=0.96,
                rationale=(f"A matching appointment or reservation is already on the calendar for "
                           f"{event_date.isoformat()}."),
                payload={**payload, "calendar_match": True},
            )
        return ProposedAction(
            kind=ActionKind.CREATE_TASK, title=title,
            confidence=0.94 if explicit else 0.86,
            rationale=(f"The email is a reminder for {event_date.isoformat()}, and no matching "
                       "calendar item was found. Add it to the calendar and then handle the email."),
            payload={**payload, "calendar_match": False},
        )

    @classmethod
    def _matching_calendar_item(cls, email_text: str,
                                calendar_items: list[dict[str, str]]) -> bool:
        email_tokens = _tokens_without(email_text, cls.CALENDAR_STOP_WORDS)
        for item in calendar_items:
            item_title = str(item.get("title", ""))
            item_tokens = _tokens_without(item_title, cls.CALENDAR_STOP_WORDS)
            if email_tokens & item_tokens:
                return True
            if item_title and SequenceMatcher(
                None, item_title.lower(), email_text.lower()
            ).ratio() >= 0.65:
                return True
        return False

    @staticmethod
    def _calendar_task_title(email: Email, event_date: date | None) -> str:
        subject = re.sub(
            r"^(re|fwd|reminder|confirmation)\s*:\s*", "", email.subject,
            flags=re.I,
        ).strip()
        subject = subject or "appointment or reservation"
        suffix = f" ({event_date.isoformat()})" if event_date else ""
        return f"Add {subject} to calendar{suffix}"

    def _process_with_rules(self, email: Email,
                            thread: list[Email]) -> tuple[str, ProposedAction]:
        text = f"{email.subject}. {email.body}".strip()
        summary = self._summary(email)
        if not any(term in text.lower() for term in self.ACTION_TERMS):
            return summary, ProposedAction(
                kind=ActionKind.NONE,
                title=email.subject,
                confidence=0.9,
                rationale="No request, commitment, or deadline was detected.",
            )

        due_date, explicit = self._extract_due_date(text, email.received_at.date())
        title = self._task_title(email)
        duplicate = self._find_duplicate(title)
        confidence = 0.93 if explicit else 0.76
        if duplicate:
            return summary, ProposedAction(
                kind=ActionKind.UPDATE_TASK,
                title=title,
                confidence=max(confidence, 0.9),
                rationale=f"Related open task found: {duplicate.id}.",
                payload={"task_id": duplicate.id, "due_date": due_date, "source_url": email.web_url,
                         "source_id": email.id, "thread_messages": len(thread),
                         "email_subject": email.subject, "email_sender": email.sender},
            )
        return summary, ProposedAction(
            kind=ActionKind.CREATE_TASK,
            title=title,
            confidence=confidence,
            rationale="The email contains actionable language."
            + (" It includes an explicit date." if explicit else " The deadline is uncertain."),
            payload={"due_date": due_date, "source_url": email.web_url,
                     "source_id": email.id, "thread_messages": len(thread),
                     "email_subject": email.subject, "email_sender": email.sender},
        )

    def _process_with_reasoner(self, email: Email,
                               thread: list[Email]) -> tuple[str, ProposedAction]:
        examples = None
        if self.feedback is not None:
            examples = self.feedback.search_feedback(f"{email.subject} {email.body}", limit=3)
        analysis = self.reasoner.analyze(email, thread, examples)
        confidence = max(0.0, min(analysis.confidence, 1.0))
        if not analysis.actionable or not analysis.task_title:
            return analysis.summary, ProposedAction(
                kind=ActionKind.NONE, title=email.subject, confidence=confidence,
                rationale=analysis.rationale,
                payload={"analysis_source": "model", "email_subject": email.subject,
                         "email_sender": email.sender, "source_id": email.id,
                         "source_url": email.web_url},
            )
        duplicate = self._find_duplicate(analysis.task_title)
        kind = ActionKind.UPDATE_TASK if duplicate else ActionKind.CREATE_TASK
        payload = {
            "due_date": analysis.due_date, "source_url": email.web_url,
            "source_id": email.id, "thread_messages": len(thread),
            "analysis_source": "model",
            "email_subject": email.subject, "email_sender": email.sender,
        }
        if duplicate:
            payload["task_id"] = duplicate.id
        return analysis.summary, ProposedAction(
            kind=kind, title=analysis.task_title, confidence=confidence,
            rationale=analysis.rationale, payload=payload,
        )

    def execute(self, action: ProposedAction) -> Task:
        due = action.payload.get("due_date")
        if action.kind is ActionKind.CREATE_TASK:
            return self.tasks.create(Task(
                id=SQLiteStore.new_id("task"), title=action.title, due_date=due,
                source_url=action.payload.get("source_url"),
                source_id=action.payload.get("source_id"), status="tentative",
                notes=action.rationale,
            ))
        if action.kind is ActionKind.UPDATE_TASK:
            task = next(task for task in self.tasks.list_open() if task.id == action.payload["task_id"])
            if due:
                task.due_date = due
            task.source_url = action.payload.get("source_url") or task.source_url
            task.notes = f"{task.notes}\nUpdate: {action.rationale}".strip()
            return self.tasks.update(task)
        raise ValueError(f"Unsupported productivity action: {action.kind}")

    def _find_duplicate(self, title: str) -> Task | None:
        for task in self.tasks.list_open():
            if task.source_id and task.source_id == title:
                return task
            if SequenceMatcher(None, title.lower(), task.title.lower()).ratio() >= 0.72:
                return task
        return None

    @staticmethod
    def _summary(email: Email) -> str:
        compact = " ".join(email.body.split())
        return f"{email.sender}: {compact[:180]}" + ("…" if len(compact) > 180 else "")

    @staticmethod
    def _task_title(email: Email) -> str:
        subject = re.sub(r"^(re|fwd):\s*", "", email.subject, flags=re.I).strip()
        return subject or "Follow up on email"

    @staticmethod
    def _extract_due_date(text: str, received: date) -> tuple[date | None, bool]:
        iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
        if iso:
            return date.fromisoformat(iso.group(0)), True
        lowered = text.lower()
        if "tomorrow" in lowered:
            return received + timedelta(days=1), True
        if "next week" in lowered:
            return received + timedelta(days=7), False
        months = {
            "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
            "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
            "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
            "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
            "dec": 12, "december": 12,
        }
        named = re.search(
            r"\b(" + "|".join(months) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
            r"(?:,?\s+(20\d{2}))?\b", lowered,
        )
        if named:
            year = int(named.group(3) or received.year)
            candidate = date(year, months[named.group(1)], int(named.group(2)))
            if named.group(3) is None and candidate < received:
                candidate = candidate.replace(year=year + 1)
            return candidate, True
        return None, False


def _tokens_without(value: str, stop_words: set[str]) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 2 and token not in stop_words
    }


class PersonalizationAgent:
    def __init__(self, memory: MemoryPort) -> None:
        self.memory = memory

    def context_for(self, request: str) -> list[Memory]:
        return self.memory.search(request, limit=5)

    def propose_memory(self, text: str, source: str) -> ProposedAction:
        return ProposedAction(
            kind=ActionKind.STORE_MEMORY,
            title="Remember a personal preference",
            confidence=0.7,
            rationale="Persistent profile changes require confirmation.",
            payload={"text": text, "source": source, "category": "preference"},
        )

    def store_confirmed(self, action: ProposedAction) -> Memory:
        return self.memory.add(Memory(
            id=SQLiteStore.new_id("memory"), text=str(action.payload["text"]),
            category=str(action.payload.get("category", "preference")), confidence=1.0,
            confirmed=True, source=str(action.payload["source"]),
            created_at=datetime.now(timezone.utc),
        ))


class DiscoveryAgent:
    def __init__(self, search: SearchPort, calendar: CalendarPort) -> None:
        self.search = search
        self.calendar = calendar

    def recommend_activities(self, memories: list[Memory], start: date, end: date) -> ProposedAction:
        interests = [memory.text for memory in memories]
        candidates = self.search.activities(interests, start, end)
        evaluated = []
        for item in candidates:
            conflicts = self.calendar.conflicts_on(date.fromisoformat(item["date"])) \
                if hasattr(self.calendar, "conflicts_on") else []
            evaluated.append({
                **item, "calendar_status": "conflict" if conflicts else "available",
                "calendar_conflicts": conflicts,
            })
        return ProposedAction(
            kind=ActionKind.RECOMMEND,
            title="Family activity recommendations",
            confidence=0.88 if evaluated else 0.4,
            rationale="Candidates were ranked using retrieved preferences and calendar availability.",
            payload={"candidates": evaluated},
        )

    def summarize_news(self, memories: list[Memory]) -> ProposedAction:
        interests = [memory.text for memory in memories]
        stories = self.search.news(interests)
        return ProposedAction(
            kind=ActionKind.RECOMMEND,
            title="Personalized daily news",
            confidence=0.9 if stories else 0.4,
            rationale="Current headlines were grouped using confirmed news preferences.",
            payload={"stories": stories},
        )
