from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .model_gateway import UnlimitedLLMGateway

THRESHOLDS = {
    "screen_recall": 0.95,
    "unsupported_claim_rate_max": 0.02,
    "layer1_coverage": 0.90,
    "layer2_macro_f1": 0.80,
    "layer3_macro_f1": 0.80,
    "layer4_accuracy": 0.90,
}

CLASSIFICATION_FIELDS = {
    "skeleton_layer_2": ("label", "discourse_relation"),
    "skeleton_layer_3": ("label", "intent"),
    "skeleton_layer_4": ("label", "role"),
}


def _classification_label(
    task: str, value: dict[str, Any], *, reference: bool,
) -> str:
    """Recognize native output keys; never count two missing labels as agreement."""
    labels = [
        value[field].strip() for field in CLASSIFICATION_FIELDS[task]
        if isinstance(value.get(field), str) and value[field].strip()
    ]
    if len(set(labels)) > 1:
        raise ValueError(f"Conflicting classification fields for {task}: {labels}")
    if labels:
        return labels[0]
    if reference:
        raise ValueError(f"Reference annotation for {task} requires a nonempty label")
    return "__MISSING_PREDICTION__"


def _macro_f1(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    labels = sorted({label for pair in pairs for label in pair})
    values = []
    for label in labels:
        tp = sum(expected == label and predicted == label for expected, predicted in pairs)
        fp = sum(expected != label and predicted == label for expected, predicted in pairs)
        fn = sum(expected == label and predicted != label for expected, predicted in pairs)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        values.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(values) / len(values)


def evaluate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    split_papers: dict[str, set[str]] = defaultdict(set)
    for record in records:
        split_papers[str(record.get("split") or "unspecified")].add(record["paper_id"])
    named_splits = [
        (name, papers) for name, papers in split_papers.items() if name != "unspecified"
    ]
    for index, (name, papers) in enumerate(named_splits):
        for other_name, other_papers in named_splits[index + 1 :]:
            overlap = papers & other_papers
            if overlap:
                raise ValueError(
                    f"Papers cross evaluation splits {name}/{other_name}: {sorted(overlap)}"
                )

    screen_relevant = screen_found = 0
    unsupported = atomic_claims = 0
    layer1_expected = layer1_found = 0
    layer2_pairs: list[tuple[str, str]] = []
    layer3_pairs: list[tuple[str, str]] = []
    layer4_total = layer4_correct = 0
    for record in records:
        task = record["task"]
        expected = record.get("expected") or {}
        predicted = record.get("prediction") or {}
        if task == "screen" and expected.get("category") != "IRRELEVANT":
            screen_relevant += 1
            if predicted.get("category") not in {None, "UNKNOWN", "IRRELEVANT"}:
                screen_found += 1
        elif task == "provenance":
            unsupported += int(predicted.get("unsupported_claims", 0))
            atomic_claims += int(predicted.get("atomic_claims", 0))
        elif task == "skeleton_layer_1":
            facts = expected.get("facts")
            if not isinstance(facts, list) or not facts or not all(
                isinstance(fact, str) and fact.strip() for fact in facts
            ):
                raise ValueError("Layer 1 reference annotation requires nonempty facts")
            expected_items = set(facts)
            predicted_facts = predicted.get("facts", [])
            if not isinstance(predicted_facts, list) or not all(
                isinstance(fact, str) for fact in predicted_facts
            ):
                predicted_facts = []
            predicted_items = set(predicted_facts)
            layer1_expected += len(expected_items)
            layer1_found += len(expected_items & predicted_items)
        elif task == "skeleton_layer_2":
            layer2_pairs.append((
                _classification_label(task, expected, reference=True),
                _classification_label(task, predicted, reference=False),
            ))
        elif task == "skeleton_layer_3":
            layer3_pairs.append((
                _classification_label(task, expected, reference=True),
                _classification_label(task, predicted, reference=False),
            ))
        elif task == "skeleton_layer_4":
            layer4_total += 1
            layer4_correct += (
                _classification_label(task, expected, reference=True)
                == _classification_label(task, predicted, reference=False)
            )
    metrics = {
        "screen_recall": screen_found / screen_relevant if screen_relevant else None,
        "unsupported_claim_rate": unsupported / atomic_claims if atomic_claims else None,
        "layer1_coverage": layer1_found / layer1_expected if layer1_expected else None,
        "layer2_macro_f1": _macro_f1(layer2_pairs),
        "layer3_macro_f1": _macro_f1(layer3_pairs),
        "layer4_accuracy": layer4_correct / layer4_total if layer4_total else None,
    }
    failures = []
    gates = {}
    for name, threshold in THRESHOLDS.items():
        metric_name = "unsupported_claim_rate" if name == "unsupported_claim_rate_max" else name
        value = metrics[metric_name]
        gates[name] = None if value is None else (
            value <= threshold if name.endswith("_max") else value >= threshold
        )
        if gates[name] is False:
            failures.append({"gate": name, "value": value, "threshold": threshold})
    return {
        "records": len(records),
        "papers": len({record["paper_id"] for record in records}),
        "split_paper_counts": {name: len(papers) for name, papers in split_papers.items()},
        "metrics": metrics,
        "gates": gates,
        "passed": not failures and all(value is not None for value in gates.values()),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate PaperPool model contracts by paper split"
    )
    parser.add_argument("dataset")
    parser.add_argument("--root", default=".")
    parser.add_argument("--run-missing", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    records = [
        json.loads(line)
        for line in Path(args.dataset).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.run_missing:
        gateway = UnlimitedLLMGateway(args.root)
        for record in records:
            if "prediction" not in record:
                record["prediction"] = gateway.analyze(record["task"], record["input"])
    report = evaluate_records(records)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
