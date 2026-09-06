# Design and implementation mapping

## Goal

The system converts changing personal information into grounded, reviewable actions. It demonstrates an observe–reason–act loop while keeping higher-impact operations under human control.

## MCP integration

`mcp_server.py` is a `FastMCP` server that presents the assistant's external capabilities as MCP tools. The host/model controls tools, the application reads resources, and the user can invoke the reusable inbox-review prompt. `mcp_client_demo.py` demonstrates initialization, capability discovery, and tool invocation through a connected MCP client session.

The local deployment uses the `stdio` transport. Gmail OAuth remains a downstream credential used by the MCP server; it is not an MCP authentication credential. A future remote Streamable HTTP deployment must authenticate MCP clients independently.

## Agent responsibilities

| Submitted component | Implementation | Responsibility |
|---|---|---|
| Coordinator Agent | `CoordinatorAgent` | Routes triggers, applies policy, executes safe actions, and audits outcomes |
| Productivity Agent | `ProductivityAgent` | Interprets email, extracts deadlines, finds duplicate tasks, and prepares task writes |
| Personalization Agent | `PersonalizationAgent` | Retrieves historical preferences and requires confirmation for persistent memory |
| Discovery Agent | `DiscoveryAgent` | Combines preferences, fresh candidates, date windows, and calendar availability |

## Reasoning loop

The inbox workflow implements the following observable loop:

1. **Observe:** read a new Primary inbox message.
2. **Reason:** classify whether it is actionable and extract a possible deadline.
3. **Act:** retrieve its thread and the current task list.
4. **Observe:** identify whether a related task already exists.
5. **Reason:** choose create, update, propose, or ignore and assign confidence.
6. **Act:** the Coordinator applies the safety policy and either saves a tentative task or asks for review.
7. **Record:** persist the decision, evidence, and result in an audit log.
8. **Learn:** when the user reviews a proposal, retain that decision and explanation as a behavioral example for similar future emails.

This sequential, evidence-gathering loop is intentionally used instead of Tree of Thought for routine workflows.

## Memory model

The application separates two kinds of persistence:

- **Operational state:** task identifiers, source-message identifiers, status, and audit events are structured SQLite records. This supports exact lookup and review.
- **Personal memory:** interests and preferences are small, meaningful records containing confidence, confirmation status, source, and creation time. Retrieval returns only relevant memories.

The local system uses Ollama embeddings for semantic retrieval and caches vectors by memory and model in SQLite. This matches related concepts even when a request does not repeat a stored preference's exact words. A deterministic lexical fallback keeps workflows available if Ollama is offline. Both strategies remain behind `MemoryPort`.

Reviewed task decisions form a separate feedback memory. The Productivity Agent retrieves similar examples by email subject, sender, proposed title, and rationale before invoking a model reasoner. These examples influence classification but do not override current source evidence and are not treated as permanent personal preferences. This separation prevents one correction from silently changing the user's long-term profile.

## Guardrails

- Task writes are tentative and require high confidence for automatic creation.
- Ambiguous task interpretations are proposed but not executed.
- Calendar writes and permanent profile updates always require confirmation.
- Each task retains its source URL and source identifier.
- Existing tasks are checked before creation.
- Every decision is audit logged.
- Provider permissions can be scoped separately through adapter interfaces.

## Production integration boundaries

The protocols in `ports.py` isolate external systems from reasoning. Production implementations should use OAuth and least-privilege scopes. Reads and writes should use separate methods or credentials where the provider supports that separation.

An LLM can replace deterministic email interpretation by returning the same `ProposedAction` structure. Deterministic checks should still validate required fields, confidence thresholds, source grounding, and action permissions before any write occurs.

## Evaluation plan

A labeled email set can measure:

- action classification precision and recall;
- deadline extraction accuracy;
- duplicate-detection precision and recall;
- source-grounding rate;
- confidence calibration and escalation rate;
- latency, tool failures, and fallback success.

The current automated tests serve as initial regression evaluations for the most important behaviors.
