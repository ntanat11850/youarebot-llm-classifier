"""Evaluate zero-shot bot detection and create test-set predictions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from math import log
from pathlib import Path
from statistics import median
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.model_inference import ZeroShotBotDetector


def participant_rows(dialogs_path: Path, labels_path: Path) -> list[dict]:
    dialogs = json.loads(dialogs_path.read_text(encoding="utf-8"))
    labels = list(csv.DictReader(labels_path.open(encoding="utf-8")))
    labels_by_key = {
        (row["dialog_id"], int(row["participant_index"])): row.get("is_bot")
        for row in labels
    }
    rows = []
    for dialog_id, messages in dialogs.items():
        for participant_index in sorted({int(m["participant_index"]) for m in messages}):
            text = "\n".join(
                str(m.get("text") or "")
                for m in sorted(messages, key=lambda item: int(item.get("message", 0)))
                if int(m["participant_index"]) == participant_index
            )
            rows.append(
                {
                    "dialog_id": dialog_id,
                    "participant_index": participant_index,
                    "text": text,
                    "is_bot": labels_by_key.get((dialog_id, participant_index)),
                }
            )
    return rows


def dialog_holdout(rows: list[dict], fraction: float = 0.25) -> list[dict]:
    """Stable dialog-level split requiring no training or data fitting."""
    dialog_ids = sorted({row["dialog_id"] for row in rows})
    holdout_ids = set(dialog_ids[:: max(1, round(1 / fraction))])
    return [row for row in rows if row["dialog_id"] in holdout_ids]


def roc_auc(y: list[int], p: list[float]) -> float:
    positives = [score for target, score in zip(y, p) if target == 1]
    negatives = [score for target, score in zip(y, p) if target == 0]
    wins = sum(a > b for a in positives for b in negatives)
    ties = sum(a == b for a in positives for b in negatives)
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def metrics(y: list[int], p: list[float]) -> dict[str, float]:
    predictions = [int(score >= 0.5) for score in p]
    tp = sum(a == b == 1 for a, b in zip(y, predictions))
    fp = sum(a == 0 and b == 1 for a, b in zip(y, predictions))
    fn = sum(a == 1 and b == 0 for a, b in zip(y, predictions))
    clipped = [min(max(score, 1e-7), 1 - 1e-7) for score in p]
    return {
        "roc_auc": roc_auc(y, p),
        "accuracy": sum(a == b for a, b in zip(y, predictions)) / len(y),
        "f1": 2 * tp / max(2 * tp + fp + fn, 1),
        "log_loss": -sum(
            target * log(score) + (1 - target) * log(1 - score)
            for target, score in zip(y, clipped)
        )
        / len(y),
        "brier": sum((target - score) ** 2 for target, score in zip(y, p)) / len(y),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-dialogs", type=int)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    detector = ZeroShotBotDetector()
    train_rows = participant_rows(args.data_dir / "train.json", args.data_dir / "ytrain.csv")
    holdout = dialog_holdout(train_rows)
    if args.max_dialogs:
        keep = {row["dialog_id"] for row in holdout[: args.max_dialogs * 2]}
        holdout = [row for row in holdout if row["dialog_id"] in keep]

    started = perf_counter()
    probabilities = detector.predict_batch(
        [row["text"] for row in holdout], batch_size=args.batch_size
    )
    elapsed = perf_counter() - started
    y = [int(row["is_bot"]) for row in holdout]
    report = {
        "model": detector.model_name,
        "evaluation": "stable 25% dialog-level holdout from train",
        "participants": len(holdout),
        "dialogs": len({row["dialog_id"] for row in holdout}),
        "bot_rate": sum(y) / len(y),
        **metrics(y, probabilities),
        "total_seconds": elapsed,
        "milliseconds_per_participant": elapsed * 1000 / len(holdout),
        "median_probability": median(probabilities),
    }
    (args.output_dir / "zero_shot_metrics.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2), flush=True)

    if args.max_dialogs:
        return

    test_rows = participant_rows(args.data_dir / "test.json", args.data_dir / "ytest.csv")
    test_probabilities = detector.predict_batch(
        [row["text"] for row in test_rows], batch_size=args.batch_size
    )
    with (args.output_dir / "zero_shot_submission.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=["ID", "is_bot"])
        writer.writeheader()
        for row, probability in zip(test_rows, test_probabilities):
            writer.writerow(
                {
                    "ID": f'{row["dialog_id"]}_{row["participant_index"]}',
                    "is_bot": probability,
                }
            )


if __name__ == "__main__":
    main()
