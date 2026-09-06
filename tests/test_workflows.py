from datetime import date, datetime, timezone
import unittest

from personal_assistant.adapters import DemoCalendar, DemoInbox, DemoSearch
from personal_assistant.agents import DiscoveryAgent, PersonalizationAgent, ProductivityAgent
from personal_assistant.coordinator import CoordinatorAgent
from personal_assistant.models import ActionDecision, ActionKind, Email, Memory, Task
from personal_assistant.policy import SafetyPolicy
from personal_assistant.storage import SQLiteStore
from personal_assistant.reasoning import EmailAnalysis


def system(emails: list[Email], store: SQLiteStore | None = None) -> tuple[CoordinatorAgent, SQLiteStore]:
    store = store or SQLiteStore()
    calendar = DemoCalendar()
    coordinator = CoordinatorAgent(
        DemoInbox(emails), ProductivityAgent(store, calendar), PersonalizationAgent(store),
        DiscoveryAgent(DemoSearch(), calendar), store, SafetyPolicy(),
    )
    return coordinator, store


def email(email_id: str, subject: str, body: str) -> Email:
    return Email(email_id, "thread_1", "person@example.com", subject, body,
                 datetime(2026, 9, 3, tzinfo=timezone.utc), f"https://mail.example/{email_id}")


class StubReasoner:
    def __init__(self, analysis: EmailAnalysis) -> None:
        self.analysis = analysis

        self.feedback_examples: list[dict[str, object]] | None = None

    def analyze(self, message: Email, thread: list[Email],
                feedback_examples: list[dict[str, object]] | None = None) -> EmailAnalysis:
        self.feedback_examples = feedback_examples
        return self.analysis


class FailingReasoner:
    def analyze(self, message: Email, thread: list[Email], feedback_examples=None) -> EmailAnalysis:
        raise RuntimeError("model timeout")


class CalendarWithItems(DemoCalendar):
    def __init__(self, items: list[dict[str, str]]) -> None:
        super().__init__()
        self.items = items

    def conflicts_on(self, day: date) -> list[dict[str, str]]:
        return self.items


class WorkflowTests(unittest.TestCase):
    def test_missing_appointment_creates_add_to_calendar_task(self) -> None:
        store = SQLiteStore()
        message = email(
            "dentist", "Reminder: Nora dentist appointment",
            "This is a reminder for Nora's appointment on September 12, 2026.",
        )
        agent = ProductivityAgent(store, CalendarWithItems([]))
        _summary, action = agent.process_email(message, [message])
        action.decision = SafetyPolicy().decide(action)
        self.assertIs(action.kind, ActionKind.CREATE_TASK)
        self.assertIs(action.decision, ActionDecision.EXECUTE)
        self.assertIn("Add Nora dentist appointment to calendar", action.title)
        self.assertEqual(action.payload["event_date"], date(2026, 9, 12))
        self.assertEqual(action.payload["source_url"], message.web_url)

    def test_existing_matching_appointment_does_not_create_task(self) -> None:
        store = SQLiteStore()
        message = email(
            "dentist_existing", "Reminder: Nora dentist appointment",
            "This is a reminder for Nora's appointment on September 12, 2026.",
        )
        calendar = CalendarWithItems([
            {"title": "Nora dentist", "start": "2026-09-12T10:00:00-07:00"}
        ])
        _summary, action = ProductivityAgent(store, calendar).process_email(message, [message])
        self.assertIs(action.kind, ActionKind.NONE)
        self.assertTrue(action.payload["calendar_match"])

    def test_calendar_reminder_without_date_requires_review(self) -> None:
        store = SQLiteStore()
        message = email(
            "restaurant", "Reservation reminder",
            "Your restaurant reservation is coming up soon.",
        )
        _summary, action = ProductivityAgent(store, CalendarWithItems([])).process_email(
            message, [message]
        )
        self.assertIs(SafetyPolicy().decide(action), ActionDecision.PROPOSE)
        self.assertIsNone(action.payload["event_date"])

    def test_explicit_task_is_created_with_source_link(self) -> None:
        coordinator, store = system([email("e1", "Submit permission form",
                                                   "Please submit it by 2026-09-10.")])
        result = coordinator.monitor_inbox()[0]
        tasks = store.list_open()
        self.assertIs(result.actions[0].decision, ActionDecision.EXECUTE)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].due_date, date(2026, 9, 10))
        self.assertEqual(tasks[0].source_url, "https://mail.example/e1")

    def test_informational_email_is_ignored(self) -> None:
        coordinator, store = system([email("e2", "Newsletter", "Classroom news and photos.")])
        result = coordinator.monitor_inbox()[0]
        self.assertIs(result.actions[0].decision, ActionDecision.IGNORE)
        self.assertEqual(store.list_open(), [])

    def test_uncertain_deadline_requires_confirmation(self) -> None:
        coordinator, store = system([
            email("e3", "Bring supplies", "Please bring supplies next week.")
        ])
        result = coordinator.monitor_inbox()[0]
        self.assertIs(result.actions[0].decision, ActionDecision.PROPOSE)
        self.assertEqual(store.list_open(), [])
        self.assertEqual(len(store.pending_approvals()), 1)

    def test_duplicate_updates_existing_task(self) -> None:
        store = SQLiteStore()
        store.create(Task("task_1", "Submit permission form", source_id="old-email"))
        coordinator, _ = system(
            [email("e4", "Re: Submit permission form", "Please submit it by 2026-09-12.")],
            store,
        )
        result = coordinator.monitor_inbox()[0]
        self.assertEqual(result.actions[0].kind.value, "update_task")
        self.assertEqual(len(store.list_open()), 1)
        self.assertEqual(store.list_open()[0].due_date, date(2026, 9, 12))

    def test_activity_recommendations_use_memory(self) -> None:
        store = SQLiteStore()
        store.add(Memory("m1", "art activities for my children", "interest", 1.0, True,
                         "profile", datetime.now(timezone.utc)))
        coordinator, _ = system([], store)
        result = coordinator.find_activities(
            "art activities for my children", date(2026, 10, 1), date(2026, 11, 1)
        )
        self.assertTrue(result.actions[0].payload["candidates"])
        self.assertIn("Art", result.actions[0].payload["candidates"][0]["title"])

    def test_processed_email_is_not_handled_twice(self) -> None:
        coordinator, store = system([
            email("e5", "Submit health form", "Please submit it by 2026-09-15.")
        ])
        self.assertEqual(len(coordinator.monitor_inbox()), 1)
        self.assertEqual(coordinator.monitor_inbox(), [])
        self.assertEqual(len(store.list_open()), 1)

    def test_inbox_run_limits_new_messages(self) -> None:
        coordinator, store = system([
            email(f"limited_{index}", f"Task {index}", "Please complete this tomorrow.")
            for index in range(4)
        ])
        self.assertEqual(len(coordinator.monitor_inbox(max_items=2)), 2)
        processed = store.connection.execute(
            "SELECT COUNT(*) FROM processed_items"
        ).fetchone()[0]
        self.assertEqual(processed, 2)

    def test_model_timeout_falls_back_conservatively(self) -> None:
        store = SQLiteStore()
        message = email("fallback", "Submit form", "Please submit it by 2026-09-20.")
        agent = ProductivityAgent(store, DemoCalendar(), FailingReasoner(), store)
        _summary, action = agent.process_email(message, [message])
        self.assertEqual(action.payload["analysis_source"], "rules_fallback")
        self.assertLessEqual(action.confidence, 0.8)

    def test_model_reasoner_can_identify_implicit_task(self) -> None:
        store = SQLiteStore()
        calendar = DemoCalendar()
        message = email("e6", "Project materials", "The signed copy is still missing.")
        reasoner = StubReasoner(EmailAnalysis(
            summary="The sender says the signed copy is missing.", actionable=True,
            task_title="Send the signed project copy", due_date=None,
            explicit_deadline=False, confidence=0.72,
            rationale="The missing document implies a follow-up, but no deadline is stated.",
        ))
        coordinator = CoordinatorAgent(
            DemoInbox([message]), ProductivityAgent(store, calendar, reasoner, store),
            PersonalizationAgent(store), DiscoveryAgent(DemoSearch(), calendar), store,
        )
        result = coordinator.monitor_inbox()[0]
        self.assertIs(result.actions[0].decision, ActionDecision.PROPOSE)
        self.assertEqual(result.actions[0].payload["analysis_source"], "model")
        self.assertEqual(len(store.pending_approvals()), 1)

    def test_similar_review_feedback_is_passed_to_reasoner(self) -> None:
        store = SQLiteStore()
        store.add_feedback_example(
            "approval_1",
            {"title": "Weekly school newsletter", "rationale": "Possible task",
             "payload": {"email_subject": "School newsletter"}},
            "ignore", "Newsletters are informational unless they request a response.",
        )
        message = email("e7", "School newsletter", "This week's classroom news.")
        reasoner = StubReasoner(EmailAnalysis(
            summary="School news.", actionable=False, task_title=None, due_date=None,
            explicit_deadline=False, confidence=0.95, rationale="Informational only.",
        ))
        ProductivityAgent(store, DemoCalendar(), reasoner, store).process_email(message, [message])
        self.assertIsNotNone(reasoner.feedback_examples)
        self.assertEqual(reasoner.feedback_examples[0]["outcome"], "ignore")

    def test_content_feedback_suppresses_rejected_item_and_ranks_similar_interest(self) -> None:
        store = SQLiteStore()
        store.save_content_feedback(
            "news", "https://example.com/disliked", "Routine restaurant inspections",
            "Food", "not_interested",
        )
        store.save_content_feedback(
            "news", "https://example.com/liked", "Creative cooking ideas",
            "Food", "interested",
        )
        ranked = store.rank_content("news", [
            {"title": "Routine restaurant inspections", "url": "https://example.com/disliked",
             "topic": "Food"},
            {"title": "A chef shares creative cooking ideas", "url": "https://example.com/new",
             "topic": "Food"},
        ])
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["url"], "https://example.com/new")

    def test_completed_task_leaves_open_list(self) -> None:
        store = SQLiteStore()
        store.create(Task("task_done", "Finished task"))
        completed = store.complete_task("task_done")
        self.assertEqual(completed.status, "done")
        self.assertEqual(store.list_open(), [])
        self.assertEqual(store.list_completed()[0].id, "task_done")
        reopened = store.reopen_task("task_done")
        self.assertEqual(reopened.status, "tentative")
        self.assertEqual(store.list_completed(), [])
        self.assertEqual(store.list_open()[0].id, "task_done")


if __name__ == "__main__":
    unittest.main()
