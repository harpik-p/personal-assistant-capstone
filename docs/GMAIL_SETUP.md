# Gmail read-only setup

The Google adapters request `gmail.readonly` and `calendar.readonly`. They can read messages, threads, and calendar events but cannot send or modify email and cannot create, edit, or delete calendar events.

## 1. Create Google OAuth credentials

1. Open the Google Cloud Console and create or select a project.
2. Enable the **Gmail API** for that project.
3. Configure the OAuth consent screen. For a personal capstone, add your own Google account as a test user if the application remains in testing.
4. Create an OAuth client ID with application type **Desktop app**.
5. Download the client file and rename it `credentials.json`.
6. Put `credentials.json` in the project root.

Never commit this file. The repository ignores it automatically.

## 2. Install the Gmail dependencies

From the activated project environment:

```bash
python -m pip install -e '.[gmail]'
```

## 3. Authorize and run

```bash
personal-assistant inbox --source gmail --db assistant.db
```

On the first run, a browser opens for Google authorization. After approval, Google credentials are saved locally as `token.json`. This file is also excluded from Git.

The default Gmail query is:

```text
category:primary is:unread newer_than:7d
```

At most 25 messages are retrieved per run. Each processed Gmail message ID is recorded in SQLite, so subsequent runs skip it even when it remains unread.

## Privacy notes

- The current email interpretation is deterministic and local; email contents are not sent to an LLM.
- The application does not modify Gmail.
- Tasks are stored only in the local SQLite database.
- Delete `token.json` to revoke this application's local session, and revoke the application in your Google Account security settings if desired.
