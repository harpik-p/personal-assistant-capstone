from datetime import date
import unittest

from personal_assistant.calendar import GoogleCalendar


class Execute:
    def __init__(self, payload): self.payload = payload
    def execute(self): return self.payload


class Events:
    def __init__(self, payload): self.payload = payload
    def list(self, **kwargs): return Execute(self.payload)


class Service:
    def __init__(self, payload): self.payload = payload
    def events(self): return Events(self.payload)


class CalendarTests(unittest.TestCase):
    def test_conflicts_ignore_cancelled_and_transparent_events(self) -> None:
        calendar = GoogleCalendar("credentials.json", "token.json")
        calendar._service = Service({"items": [
            {"summary": "School event", "start": {"dateTime": "2026-09-12T10:00:00-07:00"}},
            {"summary": "Cancelled", "status": "cancelled", "start": {"date": "2026-09-12"}},
            {"summary": "Free", "transparency": "transparent", "start": {"date": "2026-09-12"}},
        ]})
        conflicts = calendar.conflicts_on(date(2026, 9, 12))
        self.assertEqual(conflicts, [{
            "title": "School event", "start": "2026-09-12T10:00:00-07:00"
        }])
        self.assertFalse(calendar.is_available(date(2026, 9, 12)))


if __name__ == "__main__":
    unittest.main()
