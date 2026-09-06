from __future__ import annotations

from pathlib import Path
from typing import Any


GOOGLE_READ_ONLY_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def google_credentials(credentials_path: str | Path, token_path: str | Path) -> Any:
    """Return OAuth credentials covering both read-only Google services."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "Google dependencies are missing. Install with: python -m pip install -e '.[gmail]'"
        ) from exc

    client_file = Path(credentials_path)
    token_file = Path(token_path)
    credentials = None
    if token_file.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_file), GOOGLE_READ_ONLY_SCOPES
        )
        if not credentials.has_scopes(GOOGLE_READ_ONLY_SCOPES):
            credentials = None
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    elif not credentials or not credentials.valid:
        if not client_file.exists():
            raise FileNotFoundError(f"OAuth client file not found: {client_file}")
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_file), GOOGLE_READ_ONLY_SCOPES
        )
        credentials = flow.run_local_server(port=0)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return credentials
