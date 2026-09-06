from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone

from .adapters import DemoCalendar, DemoInbox, DemoSearch
from .agents import DiscoveryAgent, PersonalizationAgent, ProductivityAgent
from .activities import SeattleActivitySearch
from .calendar import GoogleCalendar
from .coordinator import CoordinatorAgent
from .embeddings import OllamaEmbeddingProvider
from .gmail import GmailInbox
from .models import Email, Memory
from .news import PersonalizedNewsSearch
from .policy import SafetyPolicy
from .reasoning import OllamaEmailReasoner, OpenAIEmailReasoner
from .storage import SQLiteStore


def build_assistant(db_path: str, source: str = "demo",
                    reasoning_mode: str = "rules", live_activities: bool = False,
                    calendar_source: str = "demo") -> CoordinatorAgent:
    now = datetime.now(timezone.utc)
    demo_inbox = DemoInbox([
        Email(
            id="email_001", thread_id="thread_school", sender="teacher@example.edu",
            subject="Return field trip form",
            body="Please return the field trip permission form by 2026-09-10.",
            received_at=now, web_url="https://mail.google.com/mail/u/0/#inbox/email_001",
        ),
        Email(
            id="email_002", thread_id="thread_newsletter", sender="newsletter@example.com",
            subject="September school newsletter",
            body="Here are this month's classroom updates and photos.",
            received_at=now, web_url="https://mail.google.com/mail/u/0/#inbox/email_002",
        ),
    ])
    inbox = demo_inbox if source == "demo" else GmailInbox(
        os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        os.getenv("GMAIL_TOKEN_PATH", "token.json"),
    )
    embedder = None
    if os.getenv("ASSISTANT_MEMORY_MODE", "ollama") == "ollama":
        embedder = OllamaEmbeddingProvider(
            model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout=float(os.getenv("OLLAMA_EMBEDDING_TIMEOUT", "20")),
        )
    store = SQLiteStore(db_path, embedder=embedder)
    if not store.search("art children", limit=1):
        store.add(Memory(
            id="memory_art", text="My daughter enjoys art activities", category="interest",
            confidence=1.0, confirmed=True, source="initial profile", created_at=now,
        ))
    policy = SafetyPolicy(
        auto_action_threshold=float(os.getenv("ASSISTANT_AUTO_ACTION_THRESHOLD", "0.85")),
        confirmation_threshold=float(os.getenv("ASSISTANT_CONFIRM_THRESHOLD", "0.55")),
    )
    calendar = GoogleCalendar(
        os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json"),
        os.getenv("GMAIL_TOKEN_PATH", "token.json"),
    ) if calendar_source == "google" else DemoCalendar()
    reasoner = None
    if reasoning_mode == "openai":
        reasoner = OpenAIEmailReasoner(
            model=os.getenv("OPENAI_MODEL", ""), api_key=os.getenv("OPENAI_API_KEY")
        )
    elif reasoning_mode == "ollama":
        reasoner = OllamaEmailReasoner(
            model=os.getenv("OLLAMA_MODEL", "qwen3:4b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            timeout=float(os.getenv("OLLAMA_EMAIL_TIMEOUT", "45")),
        )
    return CoordinatorAgent(
        inbox=inbox,
        productivity=ProductivityAgent(store, calendar, reasoner, store),
        personalization=PersonalizationAgent(store),
        discovery=DiscoveryAgent(SeattleActivitySearch() if live_activities else DemoSearch(), calendar),
        audit=store,
        policy=policy,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the personal assistant capstone demo")
    parser.add_argument("workflow", choices=["inbox", "activities", "news"], nargs="?", default="inbox")
    parser.add_argument("--db", default=os.getenv("ASSISTANT_DB_PATH", "assistant.db"))
    parser.add_argument("--source", choices=["demo", "gmail"], default="demo",
                        help="Inbox source; Gmail uses read-only OAuth")
    parser.add_argument(
        "--calendar", choices=["demo", "google"],
        default=os.getenv("ASSISTANT_CALENDAR_SOURCE", "demo"),
        help="Calendar source; Google access is read-only",
    )
    parser.add_argument(
        "--reasoning", choices=["rules", "ollama", "openai"],
        default=os.getenv("ASSISTANT_REASONING_MODE", "rules"),
        help="Email interpretation engine",
    )
    parser.add_argument(
        "--max-emails", type=int, default=int(os.getenv("GMAIL_PROCESS_LIMIT", "5")),
        help="Maximum number of new messages to process in one run",
    )
    args = parser.parse_args()
    coordinator = build_assistant(
        args.db, args.source, args.reasoning, live_activities=args.workflow == "activities",
        calendar_source=args.calendar,
    )
    if args.workflow == "inbox":
        payload = [result.to_dict() for result in coordinator.monitor_inbox(max(1, args.max_emails))]
    elif args.workflow == "activities":
        today = date.today()
        payload = coordinator.find_activities(
            "weekend activities for Nora and Ozan near 98105: physical parkour arts crafts "
            "creative Pokemon space chemistry science cooking food",
            today, today + timedelta(days=60),
        ).to_dict()
    else:
        coordinator.discovery = DiscoveryAgent(PersonalizedNewsSearch(), DemoCalendar())
        payload = coordinator.daily_news(
            "news interests arts culture technology AI cats Seattle uplifting food"
        ).to_dict()
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
