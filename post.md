# LinkedIn draft

TypeSafe's Jev doesn't generate text. You give it state and a typed question; it returns one of the allowed answers with probabilities.

So I gave it a simulated version of a very Bengaluru problem: deciding who gets the green light at Sony World Signal in Koramangala.

Every 15 simulated seconds, Jev had three choices:

```text
serve_inner_ring_road
serve_80_feet_road
extend_current
```

I tested two ways of describing the same junction.

One sent raw JSON: queue lengths, oldest wait, recent arrivals, and the current signal phase.

The other translated that state into ordinary language: one road has a heavy queue, the opposing road is moving normally, and the current green has already served for a long time.

I ran three traffic scenarios—morning peak, evening peak, and rain with a temporary blockage—across three different arrival seeds. That produced 558 live Jev decisions.

The comparison:

```text
Fixed-time signal       33.42 s average wait
Max-pressure heuristic  25.09 s
Jev with prose          24.50 s
Jev with raw JSON       24.15 s
```

Raw numbers did not confuse it. In this simulation they produced the lowest average wait. The prose version had the lowest P95 wait and higher confidence, while using fewer input tokens.

All 558 decisions cost about 1.24 cents through OpenRouter.

The part I would keep in any real control system is the boundary: Jev requested the next phase, but deterministic code enforced minimum green time, clearance, starvation prevention, and emergency priority.

This was a synthetic two-road model inspired by Sony World Junction—not a model of the real signal and definitely not a deployment proposal.

But it showed something useful: typed decision models are not limited to routing emails or tickets. Put them inside a well-defined state machine, keep safety rules in code, and they can make repeated operational choices without generating a single paragraph.

Jev documentation: https://docs.typesafe.ai/introduction

Experiment source and replay: https://github.com/Akhila14/jev-traffic-simulator
