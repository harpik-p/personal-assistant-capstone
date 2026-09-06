import os
import tempfile
import unittest
import json

from mcp.shared.memory import create_connected_server_and_client_session

from personal_assistant.mcp_server import mcp


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("ASSISTANT_DB_PATH")
        os.environ["ASSISTANT_DB_PATH"] = os.path.join(self.temp_dir.name, "test.db")

    async def asyncTearDown(self) -> None:
        if self.previous_db is None:
            os.environ.pop("ASSISTANT_DB_PATH", None)
        else:
            os.environ["ASSISTANT_DB_PATH"] = self.previous_db
        self.temp_dir.cleanup()

    async def test_server_advertises_capstone_primitives(self) -> None:
        async with create_connected_server_and_client_session(mcp) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            resources = {str(resource.uri) for resource in (await session.list_resources()).resources}
            prompts = {prompt.name for prompt in (await session.list_prompts()).prompts}
        self.assertIn("gmail_process_primary_inbox", tools)
        self.assertIn("news_daily_summary", tools)
        self.assertIn("tasks_mark_complete", tools)
        self.assertIn("tasks_reopen", tools)
        self.assertIn("memory_store_confirmed", tools)
        self.assertIn("tasks://open", resources)
        self.assertIn("review_inbox", prompts)

    async def test_memory_write_requires_confirmation(self) -> None:
        async with create_connected_server_and_client_session(mcp) as session:
            await session.initialize()
            result = await session.call_tool("memory_store_confirmed", {
                "text": "I like art events", "category": "interest",
                "source": "test", "user_confirmed": False,
            })
        self.assertIn('"stored": false', result.content[0].text.lower())

    async def test_human_can_approve_edited_task(self) -> None:
        async with create_connected_server_and_client_session(mcp) as session:
            await session.initialize()
            await session.call_tool("gmail_process_primary_inbox", {"source": "demo"})
            # The demo action is high confidence, so create an uncertain approval directly
            # through the same persistent queue used by the Coordinator.
            from personal_assistant.models import ActionKind, ProposedAction
            from personal_assistant.storage import SQLiteStore

            store = SQLiteStore(os.environ["ASSISTANT_DB_PATH"])
            approval_id = store.queue_approval("test-email", ProposedAction(
                ActionKind.CREATE_TASK, "Call school", 0.7, "Deadline is ambiguous",
                {"due_date": None, "source_url": "https://mail.example/test", "source_id": "test"},
            ).to_dict())
            result = await session.call_tool("approvals_resolve", {
                "approval_id": approval_id, "decision": "approve",
                "edited_title": "Call school office", "edited_due_date": "2026-09-20",
            })
            payload = json.loads(result.content[0].text)
        self.assertEqual(payload["status"], "approved")
        self.assertEqual(payload["task"]["title"], "Call school office")
        self.assertEqual(payload["task"]["due_date"], "2026-09-20")

    async def test_human_can_reject_action(self) -> None:
        from personal_assistant.models import ActionKind, ProposedAction
        from personal_assistant.storage import SQLiteStore

        store = SQLiteStore(os.environ["ASSISTANT_DB_PATH"])
        approval_id = store.queue_approval("test-email", ProposedAction(
            ActionKind.CREATE_TASK, "Maybe a task", 0.6, "Ambiguous", {}
        ).to_dict())
        async with create_connected_server_and_client_session(mcp) as session:
            await session.initialize()
            result = await session.call_tool("approvals_resolve", {
                "approval_id": approval_id, "decision": "reject",
                "feedback": "This is only informational.",
            })
            payload = json.loads(result.content[0].text)
        self.assertEqual(payload["status"], "rejected")
        self.assertEqual(SQLiteStore(os.environ["ASSISTANT_DB_PATH"]).list_open(), [])


if __name__ == "__main__":
    unittest.main()
