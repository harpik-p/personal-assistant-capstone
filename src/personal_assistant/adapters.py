from __future__ import annotations

from datetime import date

from .models import Email


class DemoInbox:
    def __init__(self, emails: list[Email]) -> None:
        self.emails = emails

    def unread_primary(self) -> list[Email]:
        return list(self.emails)

    def thread(self, thread_id: str) -> list[Email]:
        return [email for email in self.emails if email.thread_id == thread_id]


class DemoCalendar:
    def __init__(self, busy_days: set[date] | None = None) -> None:
        self.busy_days = busy_days or set()

    def is_available(self, day: date) -> bool:
        return day not in self.busy_days

    def conflicts_on(self, day: date) -> list[dict[str, str]]:
        return [{"title": "Busy", "start": day.isoformat()}] if day in self.busy_days else []


class DemoSearch:
    def news(self, interests: list[str]) -> list[dict[str, str]]:
        return [
            {"title": f"Weekly update: {interest}", "url": f"https://example.com/{index}"}
            for index, interest in enumerate(interests[:3], start=1)
        ]

    def activities(self, interests: list[str], start: date, end: date) -> list[dict[str, str]]:
        topic = interests[0] if interests else "family"
        return [{
            "title": f"Local {topic.title()} Workshop",
            "date": start.isoformat(),
            "url": "https://example.com/activity",
            "reason": f"Matches the stored interest: {topic}",
        }]
