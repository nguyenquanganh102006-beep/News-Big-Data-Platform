import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from .accident import classify_accident, VERSION


def evaluate(samples):
    predictions = []
    for row in samples:
        decision = classify_accident(row["title"], row.get("description_text"))
        predictions.append({**row, "prediction": asdict(decision)})
    known = [r for r in predictions if r["label"] != "uncertain"]
    tp = sum(r["label"] == "accident" and r["prediction"]["label"] == "accident" for r in known)
    fp = sum(r["label"] == "not_accident" and r["prediction"]["label"] == "accident" for r in known)
    fn = sum(r["label"] == "accident" and r["prediction"]["label"] != "accident" for r in known)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    metrics = {
        "version": VERSION, "evaluation_kind": "development_resubstitution_not_independent_test",
        "samples": len(predictions), "known_label_samples": len(known),
        "known_label_exact_accuracy": sum(r["label"] == r["prediction"]["label"] for r in known) / len(known),
        "three_label_accuracy": sum(r["label"] == r["prediction"]["label"] for r in predictions) / len(predictions),
        "precision_accident": precision, "recall_accident": recall,
        "f1_accident": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "true_positive": tp, "false_positive": fp, "false_negative_including_abstentions": fn,
        "confusion_matrix_actual_to_predicted": {label: dict(Counter(r["prediction"]["label"] for r in predictions if r["label"] == label)) for label in ("accident", "not_accident", "uncertain")},
        "errors": [r["sample_id"] for r in predictions if r["label"] != r["prediction"]["label"]],
    }
    return metrics, predictions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=Path("docs/details/accident_filter/reviewed_samples.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("docs/details/accident_filter/evaluation_v1"))
    args = parser.parse_args()
    samples = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]
    metrics, predictions = evaluate(samples)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "predictions.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
