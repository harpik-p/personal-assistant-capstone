from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .google_auth import google_credentials


class GoogleCalendar:
    """Read-only availability adapter for the user's primary Google Calendar."""

    def __init__(self, credentials_path: str | Path, token_path: str | Path) -> None:
        self.credentials_path = credentials_path
        self.token_path = token_path
        self._service: Any | None = None

    @property
    def service(self) -> Any:
        if self._service is None:
            try:
                from googleapiclient.discovery import build
            except ImportError as exc:
                raise RuntimeError(
                    "Google dependencies are missing. Install with: python -m pip install -e '.[gmail]'"
                ) from exc
            self._service = build(
                "calendar", "v3",
                credentials=google_credentials(self.credentials_path, self.token_path),
                cache_discovery=False,
            )
        return self._service

    def conflicts_on(self, day: date) -> list[dict[str, str]]:
        start = datetime.combine(day, time.min, tzinfo=ZoneInfo("America/Los_Angeles"))
        end = start + timedelta(days=1)
        response = self.service.events().list(
            calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=20,
        ).execute()
        conflicts = []
        for event in response.get("items", []):
            if event.get("status") == "cancelled" or event.get("transparency") == "transparent":
                continue
            event_start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
            conflicts.append({
                "title": event.get("summary", "Busy"),
                "start": str(event_start or day.isoformat()),
            })
        return conflicts

    def is_available(self, day: date) -> bool:
        return not self.conflicts_on(day)
