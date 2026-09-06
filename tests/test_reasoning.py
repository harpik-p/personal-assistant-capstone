import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from personal_assistant.models import Email
from personal_assistant.reasoning import OllamaEmailReasoner, _thread_context


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


class OllamaReasonerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.email = Email(
            "e1", "t1", "teacher@example.edu", "Permission form",
            "Please return it by 2026-09-12.",
            datetime(2026, 9, 4, tzinfo=timezone.utc), "https://mail.example/e1",
        )

    @patch("personal_assistant.reasoning.urlopen")
    def test_parses_structured_local_model_response(self, mocked_urlopen) -> None:
        analysis = {
            "summary": "A permission form must be returned.", "actionable": True,
            "task_title": "Return permission form", "due_date": "2026-09-12",
            "explicit_deadline": True, "confidence": 0.94,
            "rationale": "The email explicitly requests the form and provides a date.",
        }
        mocked_urlopen.return_value = FakeResponse({
            "message": {"content": json.dumps(analysis)}
        })
        result = OllamaEmailReasoner().analyze(self.email, [self.email])
        self.assertTrue(result.actionable)
        self.assertEqual(result.task_title, "Return permission form")
        self.assertEqual(result.due_date.isoformat(), "2026-09-12")

    @patch("personal_assistant.reasoning.urlopen")
    def test_rejects_invalid_confidence(self, mocked_urlopen) -> None:
        analysis = {
            "summary": "Summary", "actionable": False, "task_title": None,
            "due_date": None, "explicit_deadline": False, "confidence": 4,
            "rationale": "No task.",
        }
        mocked_urlopen.return_value = FakeResponse({
            "message": {"content": json.dumps(analysis)}
        })
        with self.assertRaisesRegex(RuntimeError, "invalid structured"):
            OllamaEmailReasoner().analyze(self.email, [self.email])

    def test_thread_context_is_bounded(self) -> None:
        long_email = Email(
            "long", "t1", "person@example.com", "Long", "x" * 10000,
            datetime(2026, 9, 4, tzinfo=timezone.utc), "https://mail.example/long",
        )
        context = _thread_context([long_email] * 10)
        self.assertLessEqual(len(context), 12000)
        self.assertIn("truncated", context)


if __name__ == "__main__":
    unittest.main()
