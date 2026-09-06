from pathlib import Path
import unittest

from evaluation.run_evaluation import evaluate


class EvaluationRunnerTests(unittest.TestCase):
    def test_privacy_safe_benchmark_meets_documented_baseline(self) -> None:
        dataset = Path(__file__).parents[1] / "evaluation" / "email_cases.json"
        result = evaluate(dataset)
        metrics = result["metrics"]
        self.assertEqual(result["dataset_size"], 14)
        self.assertGreaterEqual(metrics["task_extraction_f1"], 0.8)
        self.assertEqual(metrics["source_grounding_rate"], 1.0)
        self.assertGreaterEqual(metrics["confidence_decision_accuracy"], 0.8)


if __name__ == "__main__":
    unittest.main()
