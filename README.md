# Personal Assistant Capstone

A cohesive, safety-aware multi-agent system for turning personal information into useful actions. The project demonstrates the architecture in the capstone proposal while remaining runnable without access to a real inbox or calendar.

The assistant is exposed through a **Model Context Protocol (MCP)** server built with `FastMCP`, matching the MCP client/server pattern used in the course.

Email interpretation supports reproducible local rules, free local model reasoning with Ollama, and optional OpenAI API reasoning. See the [Ollama setup guide](docs/OLLAMA_SETUP.md) and [OpenAI setup guide](docs/OPENAI_SETUP.md).

## What the MVP demonstrates

- **Coordinator Agent** routes workflows, applies confidence/impact policy, and records an audit trail.
- **Productivity Agent** summarizes emails, detects actionable requests, extracts dates, checks for duplicates, and creates or updates tentative tasks.
- **Calendar reminder reconciliation** checks appointment and reservation reminders against the relevant calendar day and creates a source-linked “Add to calendar” task only when a matching event is absent.
- **Personalization Agent** stores confirmed preferences and retrieves relevant long-term context using local semantic embeddings.
- **Discovery Agent** combines current search results, retrieved preferences, and calendar availability.
- **Live activity discovery** reads public Seattle Public Library and ParentMap event data, keeps weekend events, and ranks them against the confirmed family profile.
- **Personalized news digest** selects recent, source-linked stories across confirmed topics and filters distressing local-news categories.
- **Human in the loop** receives ambiguous or high-impact actions for confirmation.
- **Behavioral feedback retrieval** uses similar approved and rejected decisions to guide later email analysis.
- **Tool boundaries** separate agent logic from Gmail, task, calendar, search, memory, and audit implementations.

The included adapters use local sample data. This makes the repository reproducible for grading and prevents accidental writes to personal accounts.

A read-only Gmail adapter is also included. Follow [the Gmail setup guide](docs/GMAIL_SETUP.md) to use your own Primary inbox.

Read-only Google Calendar conflict checking is available after following the [Calendar setup guide](docs/CALENDAR_SETUP.md).

## Architecture

```text
Inbox or user trigger
        |
        v
 Coordinator Agent -----> Safety Policy -----> execute / propose / ignore
    |       |    |
    v       v    v
Productivity Personalization Discovery
    |       |    |
 tasks   memory  search + calendar
        \   |   /
         Audit log
```

Operational records (tasks, source-message IDs, reviewed decisions, and audit events) are kept in SQLite. Personal preferences are stored separately as meaningful memory records with confidence, confirmation, source, and recency metadata. Ollama's local `nomic-embed-text` model creates semantic vectors that are cached in SQLite. If Ollama is temporarily unavailable, retrieval safely falls back to deterministic keyword matching.

## Run it

Python 3.11 or later is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
ollama pull nomic-embed-text
personal-assistant inbox --db demo.db
personal-assistant activities --db demo.db
```

Set `ASSISTANT_MEMORY_MODE=lexical` only when running without Ollama. Semantic
retrieval is the default; `OLLAMA_EMBEDDING_MODEL` can select another installed
embedding model.

## Run the MCP demonstration

The demonstration creates an in-memory MCP client/server connection, performs the capability handshake, lists tools/resources/prompts, and invokes the inbox tool:

```bash
personal-assistant-mcp-demo --source demo
```

Run the MCP server as a standalone local process using the default `stdio` transport:

```bash
personal-assistant-mcp
```

The server exposes these model-controlled tools:

- `gmail_process_primary_inbox`
- `tasks_list_open`
- `tasks_create_tentative`
- `approvals_list_pending`
- `approvals_resolve`
- `memory_search`
- `memory_store_confirmed`
- `activities_recommend`
- `news_daily_summary`

It also exposes the read-only resources `tasks://open`, `approvals://pending`, `profile://preferences`, and `audit://recent`, plus the user-controlled `review_inbox` prompt.

## Human approval workflow

When confidence is not high enough for a safe automatic action, the Coordinator stores the proposal in the approval queue. An MCP host can call `approvals_list_pending` to display it, then call `approvals_resolve` with `approve` or `reject`. Approval can include a corrected title or due date; rejection can include feedback. Every resolution is audit logged and saved as a reviewed example. Before later model-based email analysis, the Productivity Agent retrieves up to three similar examples and supplies them as guidance. Current email evidence always takes priority, and review feedback is not automatically promoted to a permanent personal preference.

After configuring Gmail OAuth, invoke the same MCP tool against Gmail with:

```bash
personal-assistant-mcp-demo --source gmail --reasoning rules
```

To enable structured model reasoning after configuring the API credentials:

```bash
personal-assistant-mcp-demo --source gmail --reasoning openai
```

To use a free local model after installing Ollama and downloading the model:

```bash
personal-assistant-mcp-demo --source gmail --reasoning ollama
```

## Local decision dashboard

The dashboard displays live tasks and pending approvals from `assistant.db`. It runs only on localhost and does not expose the database publicly. Start both the interface and its local data service with:

```bash
cd dashboard
./start-local.sh
```

Open <http://localhost:3000>. You can edit a proposed task title or due date, approve it, reject it, and optionally record feedback. Decisions update SQLite, are added to the audit log, and become examples that help with similar emails later. The dashboard displays the number of learned examples.

Run `personal-assistant activities --db assistant.db` to refresh weekend recommendations for the next 60 days. The local dashboard displays the most recent set with source links. Activity information can change, so opening the source page before making plans remains important.

Add `--calendar google` after Calendar OAuth setup to check the primary calendar and label each recommendation with its conflict status.

Run `personal-assistant news --db assistant.db` to refresh the daily digest. The MCP server exposes the same workflow as `news_daily_summary`. Results are current headlines grouped by confirmed interests, include publication attribution, and link through Google News RSS.

News and activity cards include **Interested** and **Not interested** controls. Feedback is stored locally, exact rejected items are suppressed from later refreshes, and related future items are re-ranked using topic and keyword similarity.

Open tasks include a completion checkbox and a direct **Open email** source link in the dashboard. Completed tasks leave the open list, remain available under **Show completed**, retain their source link, and can be returned with **Reopen**. MCP clients can use `tasks_mark_complete` and `tasks_reopen` for the same reversible workflow.

To process your real unread Primary inbox after completing OAuth setup:

```bash
python -m pip install -e '.[gmail]'
personal-assistant inbox --source gmail --calendar google --db assistant.db
```

Scheduled/local-model runs process at most five new messages at a time by default. Use `--max-emails` to change the batch size. Model context is limited to the five newest thread messages, long bodies are truncated, and Ollama has a 45-second per-message limit with bounded output. If one model call fails or times out, conservative local rules analyze that message with confidence capped below the automatic-action threshold. Each completed message is committed independently, so a later failure does not discard earlier results.

The inbox demo contains one actionable school email and one informational newsletter. The first run creates a tentative task linked to its source. Later runs recognize the existing task and update it rather than creating duplicates.

With `--calendar google`, appointment and reservation reminders are compared with event titles on the relevant day. A missing event produces a linked task; a matching event produces no duplicate work. An unclear date or failed calendar check is sent for confirmation instead of being assumed.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The test suite covers task creation, source grounding, non-actionable mail, uncertain deadlines, duplicate handling, memory-informed recommendations, and retrieval of reviewed decisions.

## Evaluation

The repository includes a privacy-safe labeled benchmark and reproducible metric runner:

```bash
PYTHONPATH=src python evaluation/run_evaluation.py
```

See [the evaluation report](docs/EVALUATION.md) for results, error analysis, and limitations. The dataset is deliberately synthetic so no private Gmail content is committed.

## Safety policy

| Action | High confidence | Medium confidence | Low confidence |
|---|---|---|---|
| Tentative task create/update | Execute | Ask | Ignore |
| Calendar write | Ask | Ask | Ignore |
| Permanent profile memory | Ask | Ask | Ignore |

Calendar writes and permanent memory changes always require confirmation. All workflow decisions are written to the audit log.

## Connected services

The current implementation includes read-only Gmail inbox/thread retrieval, read-only Google Calendar conflict checks, current news and Seattle activity sources, local SQLite tasks, and Ollama-backed vector memory. The interfaces in `src/personal_assistant/ports.py` keep these integrations replaceable—for example, a future task provider can replace local tasks without changing agent reasoning.

Keep credentials in environment variables or a secret manager. Never commit `.env`, OAuth tokens, or the generated SQLite database.

## Repository roadmap

- Add optional calendar-event creation behind explicit approval; Gmail and Calendar reads are implemented.
- Add an optional external task-provider adapter; the current dashboard provides approval and task management.
- Preserve one task per email as the intentional workflow unit; notes and the source link retain its combined context.
- Add stronger retry and performance controls for scheduled execution.
- Expand the labeled evaluation with anonymized real-world cases and model-confidence calibration.
