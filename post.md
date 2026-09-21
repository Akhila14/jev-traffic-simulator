I tried Jev on a small decision we would normally solve with control logic: which side of a traffic signal should get the green light next?

I built a synthetic two-road simulation inspired by Sony World Junction in Bengaluru.

Every 15 simulated seconds, Jev received a small traffic snapshot:

- how many vehicles were waiting on each road;
- how long the oldest vehicle had waited;
- recent arrivals;
- which road currently had green.

It could choose only one of three actions: keep the current green, serve Inner Ring Road, or serve 80 Feet Road.

For the short video, I compared it with a fixed timer that changed direction every 30 seconds regardless of traffic.

```text
Jev                 24.15 s average wait
Fixed timer         33.42 s
```

That comparison shows the value of reacting to current conditions, but a fixed timer is a simple baseline. As a stronger check, I also tested a hand-written traffic-aware rule. It averaged 25.09 seconds—very close to Jev's 24.15 seconds. I left it out of the video to keep the story readable, but not out of the results.

The useful finding is not that Jev “won.” It is that Jev stayed close to a purpose-built deterministic rule while returning a typed decision and probabilities that code could use directly.

Safety remained ordinary code: minimum green time, clearance, starvation prevention and emergency priority were never delegated to the model.

The experiment covered 36 runs and 558 live Jev decisions. Total inference cost was about 1.24 cents.

This is a synthetic experiment—not real Sony World traffic data or a proposal to operate a traffic signal.

Experiment and source: https://github.com/Akhila14/jev-traffic-simulator

Jev documentation: https://docs.typesafe.ai/introduction
