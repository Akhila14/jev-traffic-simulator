#!/usr/bin/env python3
"""Aggregate replicated simulator results into JSON and CSV."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path


METRICS = (
    "average_wait_s",
    "p95_wait_s",
    "average_queue_vehicles",
    "maximum_queue_vehicles",
    "remaining_queue",
    "phase_changes",
    "safety_overrides",
    "average_confidence",
    "low_confidence_decisions",
    "average_api_latency_s",
    "api_cost_usd",
)


def mean_defined(rows, key):
    values = [row[key] for row in rows if row[key] is not None]
    return round(statistics.fmean(values), 4) if values else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    args = parser.parse_args()
    rows = json.loads((args.results_dir / "summary.json").read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["controller"])].append(row)

    aggregate = []
    for (scenario, controller), members in sorted(grouped.items()):
        item = {
            "scenario": scenario,
            "controller": controller,
            "replicates": len(members),
            "live_decisions": sum(row["decision_count"] for row in members) if controller.startswith("jev_") else 0,
        }
        item.update({metric: mean_defined(members, metric) for metric in METRICS})
        item["api_cost_usd"] = round(sum(row["api_cost_usd"] for row in members), 8)
        aggregate.append(item)

    controllers = sorted({row["controller"] for row in rows})
    overall = []
    for controller in controllers:
        members = [row for row in rows if row["controller"] == controller]
        item = {"controller": controller, "runs": len(members)}
        item.update({metric: mean_defined(members, metric) for metric in METRICS})
        item["api_cost_usd"] = round(sum(row["api_cost_usd"] for row in members), 8)
        item["live_decisions"] = sum(row["decision_count"] for row in members) if controller.startswith("jev_") else 0
        overall.append(item)

    payload = {
        "aggregate_by_scenario": aggregate,
        "overall": overall,
        "total_live_decisions": sum(item["live_decisions"] for item in overall),
        "total_api_cost_usd": round(sum(item["api_cost_usd"] for item in overall), 8),
    }
    (args.results_dir / "aggregate.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with (args.results_dir / "aggregate.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(aggregate[0]))
        writer.writeheader()
        writer.writerows(aggregate)
    print(json.dumps(payload["overall"], indent=2))
    print(f"total_live_decisions={payload['total_live_decisions']}")
    print(f"total_api_cost_usd={payload['total_api_cost_usd']}")


if __name__ == "__main__":
    main()
