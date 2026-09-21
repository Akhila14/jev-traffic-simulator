#!/usr/bin/env python3
"""Run every controller/scenario pair and write reproducible result files."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from sony_signal_sim import SCENARIOS, SIMULATION_SECONDS, run_one


CONTROLLERS = ("fixed_time", "max_pressure", "jev_raw", "jev_prose")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("results"))
    parser.add_argument("--duration", type=int, default=SIMULATION_SECONDS)
    parser.add_argument("--baselines-only", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--replicates", type=int, default=1)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    controllers = CONTROLLERS[:2] if args.baselines_only else CONTROLLERS
    jobs = [(scenario, controller, replicate) for scenario in SCENARIOS for controller in controllers for replicate in range(1, args.replicates + 1)]
    summaries = []

    def execute(item):
        scenario, controller, replicate = item
        result, trace = run_one(scenario, controller, args.duration, replicate)
        return scenario, controller, replicate, result, trace

    with ThreadPoolExecutor(max_workers=min(args.workers, len(jobs))) as executor:
        futures = {executor.submit(execute, job): job for job in jobs}
        for future in as_completed(futures):
            scenario, controller, replicate, result, trace = future.result()
            payload = {"summary": result, "trace": trace}
            path = args.output_dir / f"{scenario}--{controller}--r{replicate}.json"
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            summaries.append(result)
            print(f"completed {scenario}/{controller}/r{replicate}")

    summaries.sort(key=lambda item: (item["scenario"], CONTROLLERS.index(item["controller"]), item["replicate"]))
    (args.output_dir / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(summaries)} runs to {args.output_dir}")


if __name__ == "__main__":
    main()
