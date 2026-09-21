#!/usr/bin/env python3
"""Sony World Junction-inspired traffic simulator for typed decision experiments.

This is a synthetic two-corridor model, not a representation of the real signal
controller, lane geometry, demand counts, or Bengaluru Traffic Police policy.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import os
import random
import statistics
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


INNER_RING = "inner_ring_road"
EIGHTY_FEET = "koramangala_80_feet_road"
CORRIDORS = (INNER_RING, EIGHTY_FEET)

MIN_GREEN_SECONDS = 15
MAX_GREEN_SECONDS = 60
MAX_RED_WAIT_SECONDS = 75
CLEARANCE_SECONDS = 4
DECISION_INTERVAL_SECONDS = 15
SIMULATION_SECONDS = 480


@dataclass
class Decision:
    requested: str
    confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    latency_s: float | None = None
    cost_usd: float = 0.0


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    seed: int
    emergency_events: tuple[tuple[int, str], ...] = ()

    def arrival_rate(self, second: int, corridor: str) -> float:
        if self.name == "morning_peak":
            if corridor == INNER_RING:
                return 0.82 if second < 270 else 0.62
            return 0.34 if second < 270 else 0.48
        if self.name == "evening_peak":
            if corridor == INNER_RING:
                return 0.40 if second < 210 else 0.57
            return 0.58 if second < 210 else 0.84
        if self.name == "rain_and_blockage":
            return 0.62 if corridor == INNER_RING else 0.55
        raise ValueError(f"unknown scenario: {self.name}")

    def discharge_rate(self, second: int, corridor: str) -> float:
        rate = 1.70
        if self.name == "rain_and_blockage":
            rate *= 0.78
            if corridor == INNER_RING and 180 <= second < 315:
                rate *= 0.58
        return rate


SCENARIOS = {
    "morning_peak": Scenario(
        "morning_peak",
        "Heavy inbound Inner Ring Road demand, then a smaller late surge on 80 Feet Road.",
        23011,
    ),
    "evening_peak": Scenario(
        "evening_peak",
        "Growing outbound demand on Koramangala 80 Feet Road.",
        23029,
    ),
    "rain_and_blockage": Scenario(
        "rain_and_blockage",
        "Reduced wet-weather discharge, a temporary Inner Ring Road blockage, and an emergency vehicle.",
        23041,
        ((235, INNER_RING),),
    ),
}


def poisson(rng: random.Random, lam: float) -> int:
    """Knuth sampler; rates here are small enough for this to be inexpensive."""
    limit = math.exp(-lam)
    product = 1.0
    count = 0
    while product > limit:
        count += 1
        product *= rng.random()
    return count - 1


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(pct * len(ordered)) - 1))
    return ordered[index]


class FixedTimeController:
    name = "fixed_time"

    def decide(self, snapshot: dict[str, Any]) -> Decision:
        if snapshot["green_elapsed_s"] >= 30:
            return Decision("serve_80_feet_road" if snapshot["current_green"] == INNER_RING else "serve_inner_ring_road")
        return Decision("extend_current")


class MaxPressureController:
    name = "max_pressure"

    def decide(self, snapshot: dict[str, Any]) -> Decision:
        pressure = {}
        for corridor in CORRIDORS:
            item = snapshot["corridors"][corridor]
            pressure[corridor] = item["queue_vehicles"] + 0.08 * item["oldest_wait_s"]
        best = max(pressure, key=pressure.get)
        current = snapshot["current_green"]
        if best == current or pressure[best] < pressure[current] * 1.08:
            return Decision("extend_current")
        return Decision("serve_inner_ring_road" if best == INNER_RING else "serve_80_feet_road")


class OpenRouterJevClient:
    """Small persistent client for OpenRouter's alpha decisions endpoint."""

    def __init__(self, api_key: str, model: str = "typesafe/jev-1.13"):
        self.api_key = api_key
        self.model = model
        self.connection: http.client.HTTPSConnection | None = None

    def _connection(self) -> http.client.HTTPSConnection:
        if self.connection is None:
            self.connection = http.client.HTTPSConnection("openrouter.ai", timeout=30)
        return self.connection

    def decide(self, state: str | dict[str, Any]) -> tuple[dict[str, Any], float]:
        payload = {
            "model": self.model,
            "state": state,
            "questions": {
                "phase": {
                    "type": "choice",
                    "instructions": (
                        "Choose the next requested signal phase for this simulated junction. "
                        "Minimize total waiting and prevent starvation. Prefer extending the current green "
                        "when queues are balanced because switching has a four-second clearance cost. "
                        "An external deterministic safety layer enforces timing and emergency constraints."
                    ),
                    "criteria": {
                        "serve_inner_ring_road": "Request green for the Inner Ring Road / 100 Feet Road corridor.",
                        "serve_80_feet_road": "Request green for the Koramangala 80 Feet Road corridor.",
                        "extend_current": "Keep the current green phase to continue clearing its queue and avoid switching loss.",
                    },
                }
            },
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded)),
            "User-Agent": "jev-sony-signal-experiment/1.0",
            "X-Title": "jev-sony-signal-experiment",
            "HTTP-Referer": "https://github.com/okooo5km/jev",
        }
        last_error: Exception | None = None
        for attempt in range(4):
            started = time.perf_counter()
            try:
                conn = self._connection()
                conn.request("POST", "/api/alpha/decisions", body=encoded, headers=headers)
                response = conn.getresponse()
                raw = response.read().decode("utf-8", "replace")
                latency = time.perf_counter() - started
                if response.status == 200:
                    return json.loads(raw), latency
                if response.status == 429 or response.status >= 500:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise RuntimeError(f"OpenRouter HTTP {response.status}: {raw[:300]}")
            except (OSError, http.client.HTTPException) as exc:
                last_error = exc
                if self.connection is not None:
                    self.connection.close()
                self.connection = None
                time.sleep(0.5 * (2**attempt))
        raise RuntimeError(f"OpenRouter request failed: {last_error}")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class JevController:
    def __init__(self, mode: str, client: OpenRouterJevClient):
        if mode not in ("raw", "prose"):
            raise ValueError("mode must be raw or prose")
        self.mode = mode
        self.client = client
        self.name = f"jev_{mode}"

    def decide(self, snapshot: dict[str, Any]) -> Decision:
        state: str | dict[str, Any] = snapshot if self.mode == "raw" else prose_state(snapshot)
        response, latency = self.client.decide(state)
        answer = response["answers"]["phase"]
        usage = response.get("usage") or {}
        return Decision(
            requested=answer["choice"],
            confidence=float(answer.get("confidence", 0.0)),
            probabilities={k: float(v) for k, v in (answer.get("probabilities") or {}).items()},
            latency_s=latency,
            cost_usd=float(usage.get("cost") or 0.0),
        )


def level(value: int, bounds: tuple[int, int, int, int], labels: tuple[str, str, str, str, str]) -> str:
    for boundary, label in zip(bounds, labels):
        if value < boundary:
            return label
    return labels[-1]


def prose_state(snapshot: dict[str, Any]) -> str:
    current = "Inner Ring Road / 100 Feet Road" if snapshot["current_green"] == INNER_RING else "Koramangala 80 Feet Road"
    parts = [f"The current green serves {current}."]
    elapsed = snapshot["green_elapsed_s"]
    if elapsed < MIN_GREEN_SECONDS:
        parts.append("The current green is still in its minimum service period.")
    elif elapsed >= 50:
        parts.append("The current green has already run for a long time.")
    else:
        parts.append("The current green has completed its minimum service period.")

    descriptions = {}
    for corridor in CORRIDORS:
        item = snapshot["corridors"][corridor]
        queue_band = level(item["queue_vehicles"], (4, 10, 20, 35), ("almost empty", "light", "moderate", "heavy", "severe"))
        wait_band = level(item["oldest_wait_s"], (10, 25, 45, 65), ("very short", "short", "noticeable", "long", "close to the starvation limit"))
        arrival_band = level(item["recent_arrivals_30s"], (7, 13, 20, 28), ("very light", "light", "steady", "heavy", "surging"))
        name = "Inner Ring Road" if corridor == INNER_RING else "Koramangala 80 Feet Road"
        descriptions[corridor] = (queue_band, wait_band, arrival_band)
        parts.append(f"{name} has a {queue_band} queue, its oldest wait is {wait_band}, and recent arrivals are {arrival_band}.")

    inner_q = snapshot["corridors"][INNER_RING]["queue_vehicles"]
    eighty_q = snapshot["corridors"][EIGHTY_FEET]["queue_vehicles"]
    if max(inner_q, eighty_q) >= 1.7 * max(1, min(inner_q, eighty_q)):
        larger = "Inner Ring Road" if inner_q > eighty_q else "Koramangala 80 Feet Road"
        parts.append(f"The {larger} queue is much larger than the opposing corridor.")
    else:
        parts.append("The two queues are of broadly comparable size.")

    emergency = snapshot.get("pending_emergency")
    if emergency:
        name = "Inner Ring Road" if emergency == INNER_RING else "Koramangala 80 Feet Road"
        parts.append(f"An emergency vehicle is waiting on {name}.")
    return " ".join(parts)


class Simulator:
    def __init__(self, scenario: Scenario, controller: Any, duration: int = SIMULATION_SECONDS, replicate: int = 1):
        self.scenario = scenario
        self.controller = controller
        self.duration = duration
        self.replicate = replicate
        self.rng = random.Random(scenario.seed + (replicate - 1) * 9973)
        self.queues = {corridor: deque() for corridor in CORRIDORS}
        self.recent_arrivals = {corridor: deque() for corridor in CORRIDORS}
        self.service_credit = {corridor: 0.0 for corridor in CORRIDORS}
        self.phase = INNER_RING
        self.target_phase = INNER_RING
        self.transition_remaining = 0
        self.green_elapsed = 0
        self.arrived = 0
        self.departed = 0
        self.waits: list[float] = []
        self.max_queue = 0
        self.max_wait = 0.0
        self.queue_area = 0
        self.phase_changes = 0
        self.safety_overrides = 0
        self.decision_records: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self.pending_emergency: str | None = None
        self.emergency_delays: list[float] = []

    def oldest_wait(self, corridor: str, second: int) -> int:
        return int(second - self.queues[corridor][0][0]) if self.queues[corridor] else 0

    def snapshot(self, second: int) -> dict[str, Any]:
        return {
            "time_s": second,
            "current_green": self.phase,
            "green_elapsed_s": self.green_elapsed,
            "clearance_active": self.transition_remaining > 0,
            "pending_emergency": self.pending_emergency,
            "corridors": {
                corridor: {
                    "queue_vehicles": len(self.queues[corridor]),
                    "oldest_wait_s": self.oldest_wait(corridor, second),
                    "recent_arrivals_30s": len(self.recent_arrivals[corridor]),
                }
                for corridor in CORRIDORS
            },
        }

    def apply_safety(self, decision: Decision, second: int) -> tuple[str, str]:
        requested_corridor = {
            "serve_inner_ring_road": INNER_RING,
            "serve_80_feet_road": EIGHTY_FEET,
            "extend_current": self.phase,
        }.get(decision.requested, self.phase)
        applied = requested_corridor
        reason = "model_or_controller"
        other = EIGHTY_FEET if self.phase == INNER_RING else INNER_RING

        if self.pending_emergency and self.pending_emergency != self.phase:
            applied = self.pending_emergency
            reason = "emergency_priority"
        elif self.oldest_wait(other, second) >= MAX_RED_WAIT_SECONDS:
            applied = other
            reason = "anti_starvation"
        elif self.green_elapsed >= MAX_GREEN_SECONDS and self.queues[other]:
            applied = other
            reason = "maximum_green"
        elif applied != self.phase and self.green_elapsed < MIN_GREEN_SECONDS:
            applied = self.phase
            reason = "minimum_green"

        if applied != requested_corridor:
            self.safety_overrides += 1
        return applied, reason

    def switch_if_needed(self, requested_phase: str) -> None:
        if requested_phase == self.phase or self.transition_remaining:
            return
        self.target_phase = requested_phase
        self.transition_remaining = CLEARANCE_SECONDS
        self.phase_changes += 1

    def tick_arrivals(self, second: int) -> None:
        for corridor in CORRIDORS:
            arrivals = poisson(self.rng, self.scenario.arrival_rate(second, corridor))
            for _ in range(arrivals):
                self.queues[corridor].append((second, False))
                self.recent_arrivals[corridor].append(second)
            self.arrived += arrivals
            while self.recent_arrivals[corridor] and self.recent_arrivals[corridor][0] < second - 29:
                self.recent_arrivals[corridor].popleft()
        for event_second, corridor in self.scenario.emergency_events:
            if event_second == second:
                self.queues[corridor].appendleft((second, True))
                self.pending_emergency = corridor
                self.arrived += 1

    def tick_service(self, second: int) -> None:
        if self.transition_remaining:
            self.transition_remaining -= 1
            if self.transition_remaining == 0:
                self.phase = self.target_phase
                self.green_elapsed = 0
            return
        self.green_elapsed += 1
        corridor = self.phase
        self.service_credit[corridor] += self.scenario.discharge_rate(second, corridor)
        while self.service_credit[corridor] >= 1 and self.queues[corridor]:
            arrival_second, emergency = self.queues[corridor].popleft()
            wait = second - arrival_second
            self.waits.append(wait)
            self.departed += 1
            self.service_credit[corridor] -= 1
            if emergency:
                self.emergency_delays.append(wait)
                self.pending_emergency = None
        self.service_credit[corridor] = min(self.service_credit[corridor], 2.0)

    def run(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        for second in range(self.duration):
            self.tick_arrivals(second)
            self.tick_service(second)
            snapshot = self.snapshot(second)

            if second > 0 and second % DECISION_INTERVAL_SECONDS == 0 and not self.transition_remaining:
                decision = self.controller.decide(snapshot)
                applied, safety_reason = self.apply_safety(decision, second)
                self.switch_if_needed(applied)
                self.decision_records.append({
                    "time_s": second,
                    "requested": decision.requested,
                    "applied_phase": applied,
                    "safety_reason": safety_reason,
                    "confidence": decision.confidence,
                    "probabilities": decision.probabilities,
                    "latency_s": decision.latency_s,
                    "cost_usd": decision.cost_usd,
                })

            total_queue = sum(len(q) for q in self.queues.values())
            self.queue_area += total_queue
            self.max_queue = max(self.max_queue, total_queue)
            self.max_wait = max(self.max_wait, *(self.oldest_wait(c, second) for c in CORRIDORS))
            if second % 5 == 0:
                self.trace.append({
                    "time_s": second,
                    "inner_ring_queue": len(self.queues[INNER_RING]),
                    "eighty_feet_queue": len(self.queues[EIGHTY_FEET]),
                    "phase": "clearance" if self.transition_remaining else self.phase,
                    "inner_ring_oldest_wait_s": self.oldest_wait(INNER_RING, second),
                    "eighty_feet_oldest_wait_s": self.oldest_wait(EIGHTY_FEET, second),
                })

        confidences = [d["confidence"] for d in self.decision_records if d["confidence"] is not None]
        latencies = [d["latency_s"] for d in self.decision_records if d["latency_s"] is not None]
        result = {
            "scenario": self.scenario.name,
            "replicate": self.replicate,
            "scenario_description": self.scenario.description,
            "controller": self.controller.name,
            "duration_s": self.duration,
            "arrived": self.arrived,
            "departed": self.departed,
            "remaining_queue": sum(len(q) for q in self.queues.values()),
            "throughput_ratio": round(self.departed / self.arrived, 4) if self.arrived else 1.0,
            "average_wait_s": round(statistics.fmean(self.waits), 3) if self.waits else 0.0,
            "p95_wait_s": round(percentile(self.waits, 0.95), 3),
            "maximum_observed_wait_s": round(self.max_wait, 3),
            "average_queue_vehicles": round(self.queue_area / self.duration, 3),
            "maximum_queue_vehicles": self.max_queue,
            "phase_changes": self.phase_changes,
            "safety_overrides": self.safety_overrides,
            "emergency_delay_s": round(statistics.fmean(self.emergency_delays), 3) if self.emergency_delays else None,
            "decision_count": len(self.decision_records),
            "average_confidence": round(statistics.fmean(confidences), 4) if confidences else None,
            "low_confidence_decisions": sum(1 for c in confidences if c < 0.6),
            "average_api_latency_s": round(statistics.fmean(latencies), 4) if latencies else None,
            "api_cost_usd": round(sum(d["cost_usd"] for d in self.decision_records), 8),
            "decisions": self.decision_records,
        }
        return result, self.trace


def build_controller(name: str) -> Any:
    if name == "fixed_time":
        return FixedTimeController()
    if name == "max_pressure":
        return MaxPressureController()
    if name in ("jev_raw", "jev_prose"):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise SystemExit("OPENROUTER_API_KEY is required for Jev controllers")
        return JevController(name.removeprefix("jev_"), OpenRouterJevClient(api_key))
    raise ValueError(f"unknown controller: {name}")


def run_one(scenario_name: str, controller_name: str, duration: int = SIMULATION_SECONDS, replicate: int = 1) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    controller = build_controller(controller_name)
    try:
        return Simulator(SCENARIOS[scenario_name], controller, duration, replicate).run()
    finally:
        client = getattr(controller, "client", None)
        if client:
            client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--controller", choices=("fixed_time", "max_pressure", "jev_raw", "jev_prose"), required=True)
    parser.add_argument("--duration", type=int, default=SIMULATION_SECONDS)
    parser.add_argument("--replicate", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result, trace = run_one(args.scenario, args.controller, args.duration, args.replicate)
    payload = {"summary": result, "trace": trace}
    text = json.dumps(payload, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
