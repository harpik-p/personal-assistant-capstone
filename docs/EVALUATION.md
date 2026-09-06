# Evaluation Report

## Scope

This evaluation measures the deterministic email-analysis baseline and safety policy. It uses 14 synthetic, privacy-safe emails covering explicit tasks, implicit requests, informational messages, promotions, receipts, uncertain deadlines, source links, and a follow-up to an existing task. No personal Gmail content is included.

The dataset intentionally includes two difficult cases: an indirect request without one of the rule engine's usual action phrases, and an informational cancellation containing the misleading word “due.” Results therefore describe this small benchmark only and should not be interpreted as production-level accuracy.

## Reproduction

From the repository root, run:

```bash
PYTHONPATH=src python evaluation/run_evaluation.py
```

The labeled data is in `evaluation/email_cases.json`. The runner starts with an empty in-memory database, processes cases in a fixed order, applies the same duplicate detection and confidence policy used by the application, and prints machine-readable JSON.

## Results

| Metric | Result |
|---|---:|
| Task extraction precision | 87.5% |
| Task extraction recall | 87.5% |
| Task extraction F1 | 87.5% |
| Correct create/update/ignore action | 85.7% |
| Deadline accuracy on detected tasks | 100% |
| Source-link grounding on detected tasks | 100% |
| Confidence-policy decision accuracy | 85.7% |
| Ambiguous-case escalation rate | 66.7% |

The duplicate follow-up was correctly classified as an update rather than a new task. Every detected task retained the correct source-email URL. Explicit ISO dates and the supported relative expressions were extracted correctly in this dataset.

## Error analysis

The baseline missed “Would you mind sending the registration document…” because its transparent rules do not include that indirect phrasing. It also treated “Due to severe weather…” as potentially actionable because `due` is an action/deadline signal. The latter was proposed for review rather than executed, limiting its impact, but the implicit request was incorrectly ignored.

These errors support the hybrid design: local model reasoning handles varied and implicit language, while deterministic rules provide a fast, explainable fallback. Human review remains necessary for ambiguous results. Reviewed decisions are retained as feedback examples for later model-assisted analysis.

## Limitations and next evaluation steps

- Fourteen synthetic cases are sufficient for a reproducible capstone demonstration, not statistical validation.
- The benchmark evaluates the deterministic fallback rather than the nondeterministic Ollama or OpenAI reasoner.
- Deadline coverage is limited to formats currently supported by the rules.
- News and activity quality still requires subjective user feedback and freshness checks.
- A future evaluation should use a larger, anonymized set of real messages, multiple reviewers, and separate calibration curves for model confidence.

The automated unit suite separately verifies calendar conflict handling, semantic-memory retrieval and fallback, approval resolution, content feedback, task completion/reopening, MCP exposure, and workflow persistence.
