#!/usr/bin/env python3
"""Embed compact experiment results into the literal visualization template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    aggregate = json.loads((args.results_dir / "aggregate.json").read_text(encoding="utf-8"))
    runs = {}
    for path in sorted(args.results_dir.glob("*--r*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = dict(payload["summary"])
        summary.pop("decisions", None)
        trace = [
            [
                row["time_s"], row["inner_ring_queue"], row["eighty_feet_queue"], row["phase"],
                row["inner_ring_oldest_wait_s"], row["eighty_feet_oldest_wait_s"],
            ]
            for row in payload["trace"]
        ]
        runs[path.stem] = {"summary": summary, "trace": trace}
    data = {"aggregate": aggregate, "runs": runs}
    template = args.template.read_text(encoding="utf-8")
    if "/*__DATA__*/" not in template:
        raise SystemExit("template data marker missing")
    rendered = template.replace("/*__DATA__*/", json.dumps(data, separators=(",", ":")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
