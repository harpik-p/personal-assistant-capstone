from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import Memory, Task
from .embeddings import EmbeddingProvider


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


class SQLiteStore:
    """Structured operational state with optional local semantic memory retrieval."""

    def __init__(self, path: str | Path = ":memory:",
                 embedder: EmbeddingProvider | None = None) -> None:
        self.embedder = embedder
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        connection = getattr(self, "connection", None)
        if connection is not None:
            connection.close()
            self.connection = None  # type: ignore[assignment]

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, title TEXT NOT NULL, due_date TEXT,
              source_url TEXT, source_id TEXT UNIQUE, status TEXT NOT NULL, notes TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
              id TEXT PRIMARY KEY, text TEXT NOT NULL, category TEXT NOT NULL,
              confidence REAL NOT NULL, confirmed INTEGER NOT NULL,
              source TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memory_embeddings (
              memory_id TEXT NOT NULL, provider TEXT NOT NULL, vector TEXT NOT NULL,
              created_at TEXT NOT NULL, PRIMARY KEY(memory_id, provider),
              FOREIGN KEY(memory_id) REFERENCES memories(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS audit_log (
              id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
              details TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processed_items (
              source TEXT NOT NULL, item_id TEXT NOT NULL, processed_at TEXT NOT NULL,
              PRIMARY KEY(source, item_id)
            );
            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY, trigger TEXT NOT NULL, action TEXT NOT NULL,
              status TEXT NOT NULL, resolution TEXT, created_at TEXT NOT NULL,
              resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS feedback_examples (
              id TEXT PRIMARY KEY, approval_id TEXT UNIQUE,
              input_text TEXT NOT NULL, outcome TEXT NOT NULL,
              feedback TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS content_feedback (
              id TEXT PRIMARY KEY, content_type TEXT NOT NULL, item_key TEXT NOT NULL,
              title TEXT NOT NULL, context TEXT NOT NULL, decision TEXT NOT NULL,
              created_at TEXT NOT NULL, UNIQUE(content_type, item_key)
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_open_status
              ON tasks(status) WHERE status != 'done';
            CREATE INDEX IF NOT EXISTS idx_approvals_pending_status
              ON approvals(status) WHERE status = 'pending';
            """
        )
        self.connection.execute("PRAGMA optimize")
        self.connection.commit()
        self._backfill_feedback_examples()

    def _backfill_feedback_examples(self) -> None:
        rows = self.connection.execute(
            "SELECT id, action, status, resolution, resolved_at FROM approvals "
            "WHERE status IN ('approved', 'rejected') AND id NOT IN "
            "(SELECT approval_id FROM feedback_examples WHERE approval_id IS NOT NULL)"
        ).fetchall()
        for row in rows:
            action = json.loads(row["action"])
            resolution = json.loads(row["resolution"]) if row["resolution"] else {}
            self.connection.execute(
                "INSERT OR IGNORE INTO feedback_examples VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.new_id("feedback"), row["id"], self._feedback_input(action),
                    "task" if row["status"] == "approved" else "ignore",
                    resolution.get("feedback"),
                    row["resolved_at"] or datetime.now(timezone.utc).isoformat(),
                ),
            )
        if rows:
            self.connection.commit()

    def list_open(self) -> list[Task]:
        rows = self.connection.execute("SELECT * FROM tasks WHERE status != 'done'").fetchall()
        return [self._task(row) for row in rows]

    def list_completed(self, limit: int = 20) -> list[Task]:
        rows = self.connection.execute(
            "SELECT * FROM tasks WHERE status='done' ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._task(row) for row in rows]

    def complete_task(self, task_id: str) -> Task:
        updated = self.connection.execute(
            "UPDATE tasks SET status='done' WHERE id=? AND status!='done'", (task_id,)
        )
        if updated.rowcount != 1:
            raise ValueError("open task does not exist or is already completed")
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(row)

    def reopen_task(self, task_id: str) -> Task:
        updated = self.connection.execute(
            "UPDATE tasks SET status='tentative' WHERE id=? AND status='done'", (task_id,)
        )
        if updated.rowcount != 1:
            raise ValueError("completed task does not exist or is already open")
        self.connection.commit()
        row = self.connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task(row)

    def create(self, task: Task) -> Task:
        self.connection.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task.id, task.title, task.due_date.isoformat() if task.due_date else None,
             task.source_url, task.source_id, task.status, task.notes),
        )
        self.connection.commit()
        return task

    def update(self, task: Task) -> Task:
        self.connection.execute(
            "UPDATE tasks SET title=?, due_date=?, source_url=?, status=?, notes=? WHERE id=?",
            (task.title, task.due_date.isoformat() if task.due_date else None,
             task.source_url, task.status, task.notes, task.id),
        )
        self.connection.commit()
        return task

    def add(self, memory: Memory) -> Memory:
        self.connection.execute(
            "INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)",
            (memory.id, memory.text, memory.category, memory.confidence,
             int(memory.confirmed), memory.source, memory.created_at.isoformat()),
        )
        if self.embedder is not None:
            try:
                self._save_embedding(memory.id, self.embedder.embed(memory.text, "document"))
            except RuntimeError:
                # Memory must remain durable even when the optional local model is offline.
                pass
        self.connection.commit()
        return memory

    def search(self, query: str, limit: int = 5) -> list[Memory]:
        if self.embedder is not None:
            try:
                return self._semantic_search(query, limit)
            except RuntimeError:
                pass
        return self._lexical_search(query, limit)

    def _semantic_search(self, query: str, limit: int) -> list[Memory]:
        if self.embedder is None:
            return []
        rows = self.connection.execute("SELECT * FROM memories").fetchall()
        if not rows:
            return []
        query_vector = self.embedder.embed(query, "query")
        scored: list[tuple[float, Memory]] = []
        for row in rows:
            memory = self._memory(row)
            vector_row = self.connection.execute(
                "SELECT vector FROM memory_embeddings WHERE memory_id=? AND provider=?",
                (memory.id, self.embedder.identity),
            ).fetchone()
            if vector_row:
                vector = json.loads(vector_row["vector"])
            else:
                vector = self.embedder.embed(memory.text, "document")
                self._save_embedding(memory.id, vector)
            similarity = self._cosine(query_vector, vector)
            score = similarity + (0.05 if memory.confirmed else 0.0)
            scored.append((score, memory))
        self.connection.commit()
        return [memory for _, memory in sorted(
            scored, key=lambda item: item[0], reverse=True
        )[:limit]]

    def _lexical_search(self, query: str, limit: int) -> list[Memory]:
        query_tokens = _tokens(query)
        rows = self.connection.execute("SELECT * FROM memories").fetchall()
        memories = [self._memory(row) for row in rows]
        scored = []
        for memory in memories:
            overlap = len(query_tokens & _tokens(memory.text))
            recency = memory.created_at.timestamp() / 10**12
            score = overlap * memory.confidence + recency + (0.25 if memory.confirmed else 0)
            if overlap:
                scored.append((score, memory))
        return [memory for _, memory in sorted(scored, key=lambda item: item[0], reverse=True)[:limit]]

    def _save_embedding(self, memory_id: str, vector: list[float]) -> None:
        if self.embedder is None:
            return
        self.connection.execute(
            "INSERT OR REPLACE INTO memory_embeddings VALUES (?, ?, ?, ?)",
            (memory_id, self.embedder.identity, json.dumps(vector),
             datetime.now(timezone.utc).isoformat()),
        )

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            raise RuntimeError("Embedding vectors have incompatible dimensions")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)

    def list_memories(self, limit: int = 50) -> list[Memory]:
        rows = self.connection.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._memory(row) for row in rows]

    def recent_audit(self, limit: int = 20) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT event_type, details, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "event_type": row["event_type"],
                "details": json.loads(row["details"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def latest_activity_recommendations(self) -> list[dict[str, object]]:
        row = self.connection.execute(
            "SELECT details FROM audit_log WHERE event_type='activity_workflow' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return []
        details = json.loads(row["details"])
        actions = details.get("actions", [])
        if not actions:
            return []
        return self.decorate_content(
            "activity", list(actions[0].get("payload", {}).get("candidates", []))
        )

    def latest_news(self) -> list[dict[str, object]]:
        row = self.connection.execute(
            "SELECT details FROM audit_log WHERE event_type='news_workflow' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return []
        details = json.loads(row["details"])
        actions = details.get("actions", [])
        stories = list(actions[0].get("payload", {}).get("stories", [])) if actions else []
        return self.decorate_content("news", stories)

    def save_content_feedback(self, content_type: str, item_key: str, title: str,
                              context: str, decision: str) -> None:
        if content_type not in {"news", "activity"}:
            raise ValueError("content type must be news or activity")
        if decision not in {"interested", "not_interested"}:
            raise ValueError("decision must be interested or not_interested")
        self.connection.execute(
            "INSERT INTO content_feedback VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(content_type, item_key) DO UPDATE SET title=excluded.title, "
            "context=excluded.context, decision=excluded.decision, created_at=excluded.created_at",
            (self.new_id("content_feedback"), content_type, item_key, title, context, decision,
             datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def decorate_content(self, content_type: str,
                         items: list[dict[str, object]]) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT item_key, decision FROM content_feedback WHERE content_type=?", (content_type,)
        ).fetchall()
        decisions = {row["item_key"]: row["decision"] for row in rows}
        return [{**item, "preference": decisions.get(str(item.get("url", "")))} for item in items]

    def rank_content(self, content_type: str,
                     items: list[dict[str, str]]) -> list[dict[str, str]]:
        rows = self.connection.execute(
            "SELECT item_key, title, context, decision FROM content_feedback WHERE content_type=?",
            (content_type,),
        ).fetchall()
        scored: list[tuple[float, int, dict[str, str]]] = []
        for index, item in enumerate(items):
            item_key = item.get("url", "")
            if any(row["item_key"] == item_key and row["decision"] == "not_interested" for row in rows):
                continue
            text_tokens = _tokens(" ".join((item.get("title", ""), item.get("topic", ""),
                                             item.get("reason", ""))))
            score = 0.0
            for row in rows:
                prior_tokens = _tokens(f"{row['title']} {row['context']}")
                overlap = len(text_tokens & prior_tokens)
                if overlap:
                    score += overlap * (1 if row["decision"] == "interested" else -1)
                if row["item_key"] == item_key and row["decision"] == "interested":
                    score += 5
            scored.append((score, -index, item))
        scored.sort(key=lambda value: (value[0], value[1]), reverse=True)
        return [item for _, _, item in scored]

    def record(self, event_type: str, details: dict[str, object]) -> None:
        self.connection.execute(
            "INSERT INTO audit_log(event_type, details, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(details, default=str), datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def was_processed(self, source: str, item_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM processed_items WHERE source=? AND item_id=?", (source, item_id)
        ).fetchone()
        return row is not None

    def mark_processed(self, source: str, item_id: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO processed_items VALUES (?, ?, ?)",
            (source, item_id, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def queue_approval(self, trigger: str, action: dict[str, object]) -> str:
        approval_id = self.new_id("approval")
        self.connection.execute(
            "INSERT INTO approvals(id, trigger, action, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (approval_id, trigger, json.dumps(action, default=str), "pending",
             datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()
        return approval_id

    def pending_approvals(self) -> list[dict[str, object]]:
        rows = self.connection.execute(
            "SELECT * FROM approvals WHERE status='pending' ORDER BY created_at"
        ).fetchall()
        return [self._approval(row) for row in rows]

    def get_approval(self, approval_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            "SELECT * FROM approvals WHERE id=?", (approval_id,)
        ).fetchone()
        return self._approval(row) if row else None

    def resolve_approval(self, approval_id: str, status: str,
                         resolution: dict[str, object]) -> None:
        if status not in {"approved", "rejected"}:
            raise ValueError("approval status must be approved or rejected")
        updated = self.connection.execute(
            "UPDATE approvals SET status=?, resolution=?, resolved_at=? "
            "WHERE id=? AND status='pending'",
            (status, json.dumps(resolution, default=str),
             datetime.now(timezone.utc).isoformat(), approval_id),
        )
        if updated.rowcount != 1:
            raise ValueError("approval does not exist or has already been resolved")
        self.connection.commit()

    def add_feedback_example(self, approval_id: str, action: dict[str, object],
                             outcome: str, feedback: str | None) -> None:
        if outcome not in {"task", "ignore"}:
            raise ValueError("feedback outcome must be task or ignore")
        self.connection.execute(
            "INSERT OR REPLACE INTO feedback_examples VALUES (?, ?, ?, ?, ?, ?)",
            (
                self.new_id("feedback"), approval_id, self._feedback_input(action),
                outcome, feedback, datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.connection.commit()

    def search_feedback(self, query: str, limit: int = 3) -> list[dict[str, object]]:
        query_tokens = _tokens(query)
        rows = self.connection.execute("SELECT * FROM feedback_examples").fetchall()
        scored: list[tuple[float, dict[str, object]]] = []
        for row in rows:
            example_tokens = _tokens(row["input_text"])
            overlap = len(query_tokens & example_tokens)
            if overlap:
                union = len(query_tokens | example_tokens) or 1
                score = overlap / union
                scored.append((score, {
                    "input": row["input_text"], "outcome": row["outcome"],
                    "feedback": row["feedback"], "similarity": round(score, 3),
                }))
        return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

    def feedback_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM feedback_examples").fetchone()[0])

    @staticmethod
    def _feedback_input(action: dict[str, object]) -> str:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        subject = payload.get("email_subject", "") if isinstance(payload, dict) else ""
        sender = payload.get("email_sender", "") if isinstance(payload, dict) else ""
        return " | ".join(
            str(value) for value in [subject, sender, action.get("title", ""),
                                     action.get("rationale", "")] if value
        )

    @staticmethod
    def _approval(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"], "trigger": row["trigger"],
            "action": json.loads(row["action"]), "status": row["status"],
            "resolution": json.loads(row["resolution"]) if row["resolution"] else None,
            "created_at": row["created_at"], "resolved_at": row["resolved_at"],
        }

    @staticmethod
    def _task(row: sqlite3.Row) -> Task:
        return Task(id=row["id"], title=row["title"],
                    due_date=date.fromisoformat(row["due_date"]) if row["due_date"] else None,
                    source_url=row["source_url"], source_id=row["source_id"],
                    status=row["status"], notes=row["notes"])

    @staticmethod
    def _memory(row: sqlite3.Row) -> Memory:
        return Memory(id=row["id"], text=row["text"], category=row["category"],
                      confidence=row["confidence"], confirmed=bool(row["confirmed"]),
                      source=row["source"], created_at=datetime.fromisoformat(row["created_at"]))

    @staticmethod
    def new_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:10]}"
