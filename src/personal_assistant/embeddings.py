from __future__ import annotations

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmbeddingProvider(Protocol):
    """Produces a semantic vector for text without exposing storage concerns."""

    @property
    def identity(self) -> str: ...

    def embed(self, text: str, purpose: str = "document") -> list[float]: ...


class OllamaEmbeddingProvider:
    """Local embeddings through Ollama's /api/embed endpoint."""

    def __init__(self, model: str = "nomic-embed-text",
                 base_url: str = "http://127.0.0.1:11434", timeout: float = 20) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}:retrieval-v1"

    def embed(self, text: str, purpose: str = "document") -> list[float]:
        if purpose not in {"document", "query"}:
            raise ValueError("embedding purpose must be document or query")
        # Nomic's retrieval model is trained with distinct query/document prefixes.
        model_input = f"search_{purpose}: {text}" if self.model.startswith("nomic-") else text
        request = Request(
            f"{self.base_url}/api/embed",
            data=json.dumps({"model": self.model, "input": model_input}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            vector = payload["embeddings"][0]
            if not vector or not all(isinstance(value, (int, float)) for value in vector):
                raise ValueError("invalid vector")
            return [float(value) for value in vector]
        except HTTPError as exc:
            details = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Ollama embedding request failed ({exc.code}): {details}") from exc
        except (URLError, TimeoutError, KeyError, IndexError, TypeError, ValueError,
                json.JSONDecodeError) as exc:
            raise RuntimeError("The local embedding service is unavailable or returned invalid data") from exc
