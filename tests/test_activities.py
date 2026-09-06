from datetime import date
import unittest
from unittest.mock import patch

from personal_assistant.activities import SeattleActivitySearch


ICAL = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Kids STEM Lab
LOCATION:Northeast Branch
DTSTART:20260912T140000
DESCRIPTION:Hands-on science and engineering for children
URL:https://example.org/stem
END:VEVENT
BEGIN:VEVENT
SUMMARY:Adult Tax Help
DTSTART:20260913T120000
DESCRIPTION:Tax assistance
END:VEVENT
END:VCALENDAR
"""


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return ICAL.encode()


class ActivitySearchTests(unittest.TestCase):
    @patch("personal_assistant.activities.SeattleActivitySearch._parentmap", return_value=[])
    @patch("personal_assistant.activities.urlopen", return_value=FakeResponse())
    def test_filters_and_ranks_weekend_profile_matches(self, _urlopen, _parentmap) -> None:
        results = SeattleActivitySearch().activities(
            ["Ozan enjoys science, STEM, space, and chemistry"],
            date(2026, 9, 4), date(2026, 10, 4),
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Kids STEM Lab")
        self.assertEqual(results[0]["source"], "Seattle Public Library")


if __name__ == "__main__":
    unittest.main()
