TypeSafe's Jev is not a text-generation model. You give it a state and a typed question; it returns one of the allowed answers with probabilities.

So I gave it one of Bengaluru's more unforgiving decisions: who gets the green light at Sony World Signal in Koramangala.

I built a synthetic two-road simulation inspired by the junction.

Every few seconds, Jev received the simulated state of the junction and selected the next valid signal phase.

The state was simply:

- how many vehicles were waiting on each road;
- how long the oldest vehicle had waited;
- recent vehicle arrivals;
- which direction currently had green.

The traffic rules remained deterministic. Jev only decided which direction needed the green light next.

Minimum green time, clearance between phases, starvation prevention and emergency priority stayed in ordinary code.

I compared Jev with a fixed timer running against the same simulated traffic:

```text
Jev           24.15 s average wait
Fixed timer   33.42 s
```

A fixed timer is a simple baseline, so I also tested a hand-written traffic-aware rule. It averaged 25.09 seconds—very close to Jev. I left that comparison out of the short video to keep it readable, but not out of the published results.

The useful finding is not that Jev “won.” It is that a typed decision model stayed close to a purpose-built deterministic rule while returning a decision and probabilities that code could use directly.

The experiment covered 36 runs and 558 live Jev decisions. Total inference cost was about 1.24 cents.

This was a synthetic experiment—not real Sony World traffic data or a proposal to operate a traffic signal.

Experiment and source: https://github.com/Akhila14/jev-traffic-simulator

Jev documentation: https://docs.typesafe.ai/introduction
