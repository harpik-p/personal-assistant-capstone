# Google Calendar read-only setup

The assistant can check the primary Google Calendar for conflicts without creating, editing, or deleting events.

## Enable the API

1. Open the Google Cloud Console in the same project used for Gmail.
2. Open **APIs & Services → Library**.
3. Search for **Google Calendar API**.
4. Select it and choose **Enable**.

The existing Desktop OAuth client can be reused. No new credential file is needed.

## Grant the additional read-only scope

Delete the existing local `token.json`, then run:

```bash
personal-assistant activities --calendar google --db assistant.db
```

Google will open a new consent screen because the application now requests both `gmail.readonly` and `calendar.readonly`. If the OAuth app remains in testing, the signed-in account must still be listed as a test user.

After consent, the activity dashboard labels each recommendation with either **No calendar conflict found** or the conflicting calendar-event title. The adapter reads only the primary calendar and never writes calendar events.
