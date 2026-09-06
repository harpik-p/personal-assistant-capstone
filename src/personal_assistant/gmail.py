from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any

from .models import Email
from .google_auth import GOOGLE_READ_ONLY_SCOPES, google_credentials


SCOPES = GOOGLE_READ_ONLY_SCOPES


class GmailInbox:
    """Read-only Gmail adapter using Google's installed-app OAuth flow."""

    def __init__(self, credentials_path: str | Path, token_path: str | Path,
                 query: str = "category:primary is:unread newer_than:7d", limit: int = 25) -> None:
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.query = query
        self.limit = limit
        self._service: Any | None = None

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = self._authorize()
        return self._service

    def _authorize(self) -> Any:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Gmail dependencies are missing. Install with: python -m pip install -e '.[gmail]'"
            ) from exc

        credentials = google_credentials(self.credentials_path, self.token_path)
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def unread_primary(self) -> list[Email]:
        response = self.service.users().messages().list(
            userId="me", q=self.query, maxResults=self.limit
        ).execute()
        return [self._get_message(item["id"]) for item in response.get("messages", [])]

    def thread(self, thread_id: str) -> list[Email]:
        payload = self.service.users().threads().get(userId="me", id=thread_id, format="full").execute()
        return [self._to_email(message) for message in payload.get("messages", [])]

    def _get_message(self, message_id: str) -> Email:
        payload = self.service.users().messages().get(userId="me", id=message_id, format="full").execute()
        return self._to_email(payload)

    def _to_email(self, message: dict[str, Any]) -> Email:
        payload = message.get("payload", {})
        headers = {item["name"].lower(): item["value"] for item in payload.get("headers", [])}
        received = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=timezone.utc)
        return Email(
            id=message["id"], thread_id=message["threadId"],
            sender=self._decode_header(headers.get("from", "Unknown sender")),
            subject=self._decode_header(headers.get("subject", "(no subject)")),
            body=self._plain_text(payload), received_at=received,
            web_url=f"https://mail.google.com/mail/u/0/#inbox/{message['id']}",
        )

    @classmethod
    def _plain_text(cls, part: dict[str, Any]) -> str:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            data = part["body"]["data"]
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
        texts = [cls._plain_text(child) for child in part.get("parts", [])]
        return "\n".join(text for text in texts if text).strip()

    @staticmethod
    def _decode_header(value: str) -> str:
        return str(make_header(decode_header(value)))
