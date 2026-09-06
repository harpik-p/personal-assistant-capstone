from datetime import datetime, timezone
import unittest

from personal_assistant.models import Memory
from personal_assistant.storage import SQLiteStore


class FakeEmbedder:
    identity = "fake:test"

    def embed(self, text: str, purpose: str = "document") -> list[float]:
        lowered = text.lower()
        if "creative" in lowered or "art" in lowered:
            return [1.0, 0.0]
        if "exercise" in lowered or "gym" in lowered:
            return [0.0, 1.0]
        return [0.5, 0.5]


class FailingEmbedder:
    identity = "fake:failing"

    def embed(self, text: str, purpose: str = "document") -> list[float]:
        raise RuntimeError("offline")


class SemanticMemoryTests(unittest.TestCase):
    def test_semantic_search_matches_related_words(self) -> None:
        store = SQLiteStore(embedder=FakeEmbedder())
        now = datetime.now(timezone.utc)
        store.add(Memory("art", "Nora enjoys art projects", "interest", 1, True, "profile", now))
        store.add(Memory("gym", "Nora attends the gym", "interest", 1, True, "profile", now))
        self.assertEqual(store.search("creative activities", limit=1)[0].id, "art")
        cached = store.connection.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0]
        self.assertEqual(cached, 2)

    def test_falls_back_to_keywords_when_embeddings_are_unavailable(self) -> None:
        store = SQLiteStore(embedder=FailingEmbedder())
        store.add(Memory(
            "space", "Ozan enjoys space activities", "interest", 1, True,
            "profile", datetime.now(timezone.utc),
        ))
        self.assertEqual(store.search("space", limit=1)[0].id, "space")


if __name__ == "__main__":
    unittest.main()
