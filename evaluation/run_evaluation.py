from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from personal_assistant.adapters import DemoCalendar
from personal_assistant.agents import ProductivityAgent
from personal_assistant.models import ActionKind, Email
from personal_assistant.policy import SafetyPolicy
from personal_assistant.storage import SQLiteStore


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 3) if denominator else 0.0


def evaluate(dataset: Path) -> dict[str, object]:
    cases = json.loads(dataset.read_text())
    store = SQLiteStore()
    agent = ProductivityAgent(store, DemoCalendar())
    policy = SafetyPolicy()
    true_positive = false_positive = false_negative = 0
    decisions = deadlines = grounded = kinds = 0
    deadline_cases = grounded_cases = ambiguous_count = escalated = 0
    results: list[dict[str, object]] = []

    for case in cases:
        message = Email(
            id=case["id"], thread_id=f"thread_{case['id']}", sender="synthetic@example.com",
            subject=case["subject"], body=case["body"],
            received_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
            web_url=f"https://mail.example/{case['id']}",
        )
        _, action = agent.process_email(message, [message])
        action.decision = policy.decide(action)
        predicted_actionable = action.kind is not ActionKind.NONE
        expected_actionable = bool(case["actionable"])
        true_positive += int(predicted_actionable and expected_actionable)
        false_positive += int(predicted_actionable and not expected_actionable)
        false_negative += int(not predicted_actionable and expected_actionable)
        decisions += int(action.decision.value == case["decision"])
        kinds += int(action.kind.value == case["kind"])
        if expected_actionable:
            if predicted_actionable:
                deadline_cases += 1
                grounded_cases += 1
                actual_due = action.payload.get("due_date")
                deadlines += int(
                    (actual_due.isoformat() if actual_due else None) == case["due_date"]
                )
                grounded += int(action.payload.get("source_url") == message.web_url)
            if action.decision.value == "execute":
                agent.execute(action)
        if case["decision"] == "propose":
            ambiguous_count += 1
            escalated += int(action.decision.value == "propose")
        results.append({
            "id": case["id"], "expected_kind": case["kind"],
            "predicted_kind": action.kind.value, "expected_decision": case["decision"],
            "predicted_decision": action.decision.value,
        })

    precision = ratio(true_positive, true_positive + false_positive)
    recall = ratio(true_positive, true_positive + false_negative)
    return {
        "dataset_size": len(cases),
        "metrics": {
            "task_extraction_precision": precision,
            "task_extraction_recall": recall,
            "task_extraction_f1": ratio(2 * precision * recall, precision + recall),
            "action_kind_accuracy": ratio(kinds, len(cases)),
            "deadline_accuracy_on_detected_tasks": ratio(deadlines, deadline_cases),
            "source_grounding_rate": ratio(grounded, grounded_cases),
            "confidence_decision_accuracy": ratio(decisions, len(cases)),
            "ambiguous_case_escalation_rate": ratio(escalated, ambiguous_count),
        },
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the deterministic email baseline")
    parser.add_argument("--dataset", type=Path,
                        default=Path(__file__).with_name("email_cases.json"))
    args = parser.parse_args()
    print(json.dumps(evaluate(args.dataset), indent=2))


if __name__ == "__main__":
    main()
