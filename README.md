# Jev at a simulated Sony World Signal

This experiment asks whether TypeSafe's Jev decision model can choose traffic-signal phases in a **synthetic two-corridor simulation inspired by Sony World Junction, Koramangala, Bengaluru**.

It is not a digital twin, a proposal for deployment, or a model of the real controller. Arrival rates, road capacity, phase timings, and incidents are synthetic. Sony World was chosen because it is locally recognizable and appears in a published signal-optimisation audit covering the Inner Ring Road corridor; none of the audit's traffic measurements were used as simulator inputs. See the [B.PAC/B.MOBILE Inner Ring Road summary report](https://bpac.in/wp-content/uploads/2025/07/IRR-Summary-Report.pdf).

## What the simulator shows, in plain English

Imagine two lines of vehicles meeting at a signal. One line represents Inner Ring Road and the other represents Koramangala 80 Feet Road. New vehicles join both lines every simulated second. A green signal lets some vehicles leave; a red signal makes that line grow.

Every 15 simulated seconds, a controller looks at the situation and chooses whether to keep the current green or give the green to the other road. The page animates one previously recorded run, so you can watch the queues grow and shrink and compare four different ways of making that same decision.

The simulator is showing **decision behaviour**, not reconstructing real Sony World traffic. It answers a narrow question: given the same synthetic arrivals, does a fixed schedule, a queue-based formula, or a Jev decision produce shorter queues and waits in this small model?

What is measured:

- average wait: the mean time a simulated vehicle waited before crossing;
- P95 wait: a long-wait measure—95% of vehicles waited no longer than this;
- average queue: the average number of vehicles waiting during a run;
- model confidence: how strongly Jev preferred its selected option over the alternatives;
- API latency and cost: measured from the live Jev calls.

The animation does not contact Jev. It replays the saved JSON results from the completed experiment, which makes recording repeatable and keeps API keys out of the browser.

## Sources and what is synthetic

There are three different kinds of source material in this project:

1. **Jev behaviour and API shape:** based on TypeSafe's official documentation for typed questions, structured answers, probability distributions, and confidence.
2. **Place name and road context:** inspired by Sony World Junction and the public B.PAC/B.MOBILE Inner Ring Road report linked above.
3. **Traffic data and control rules:** created for this experiment. Arrival rates, capacity, timing, blockage, rain, emergency event, and vehicle motion are not real junction measurements.

Official Jev references:

- [TypeSafe Jev introduction](https://docs.typesafe.ai/introduction)
- [Jev quick start](https://docs.typesafe.ai/introduction/quickstart)
- [Typed primitives: Choice, Score and Noul](https://docs.typesafe.ai/primitives)
- [Confidence](https://docs.typesafe.ai/confidence)
- [HTTP API reference](https://docs.typesafe.ai/api)
- [Introducing System One Models and Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [The community `jev` CLI used during the wider evaluation](https://github.com/okooo5km/jev) — this wrapper is independent of TypeSafe; the traffic simulator called the Jev model through OpenRouter directly.

## Question

Every 15 simulated seconds, the controller chooses one typed action:

```text
serve_inner_ring_road
serve_80_feet_road
extend_current
```

We compared four controllers:

1. `fixed_time`: switch after 30 green seconds.
2. `max_pressure`: deterministic queue length plus oldest-wait heuristic.
3. `jev_raw`: Jev receives queue counts, waits, arrivals, and phase timing as JSON.
4. `jev_prose`: Jev receives the same situation translated into qualitative traffic language.

Safety is outside Jev. A deterministic layer enforces minimum/maximum green, four-second clearance, anti-starvation, and emergency priority. A model choice can request a phase; it cannot bypass these constraints.

## Scenarios and repetitions

- Morning peak: stronger Inner Ring Road demand followed by a smaller 80 Feet Road surge.
- Evening peak: growing Koramangala 80 Feet Road demand.
- Rain and blockage: reduced discharge, a temporary blockage, and an emergency vehicle.

Each scenario/controller combination ran for 480 simulated seconds across three deterministic arrival seeds: 36 runs total. The Jev controllers made 558 live decisions through OpenRouter using `typesafe/jev-1.13`.

## Results

Metrics below are unweighted means across nine runs per controller.

| Controller | Mean wait | P95 wait | Mean queue | Max queue | Mean API latency | Jev cost |
|---|---:|---:|---:|---:|---:|---:|
| Fixed time | 33.42 s | 71.56 s | 39.47 vehicles | 69.89 | — | — |
| Max pressure | 25.09 s | 52.22 s | 29.55 vehicles | 56.44 | — | — |
| Jev, raw JSON | **24.15 s** | 52.44 s | **28.47 vehicles** | **54.33** | 0.413 s | $0.00657 |
| Jev, prose | 24.50 s | **51.56 s** | 28.91 vehicles | 56.00 | 0.395 s | $0.00587 |

Total live inference cost was **$0.012446** for 558 decisions.

In this toy model, both Jev representations substantially outperformed the fixed timer and landed within a few percent of the purpose-built max-pressure heuristic. Raw JSON produced the lowest mean wait; prose produced the lowest P95 wait and much higher average model confidence (0.77 versus 0.60). The differences between the two Jev modes are small relative to the limited three-seed sample, so this is not evidence that either representation is universally better.

The deterministic safety layer overrode an average of 5.6 raw-Jev requests and 5.1 prose-Jev requests per run, mostly to enforce minimum green or prevent starvation. That is part of the design, not a hidden correction: learned judgment chooses among useful actions while ordinary code owns safety invariants.

## What this demonstrates

- Jev can participate in a repeated control loop; it is not limited to one-off ticket classification.
- Its typed answer is directly usable—no generated text or JSON extraction step.
- Numeric JSON worked at least as well as the qualitative rendering in this simulator.
- Prose required fewer input tokens, cost slightly less, and returned higher confidence.
- A typed model can complement a deterministic controller, but should not replace hard safety constraints.

It does **not** demonstrate that Jev should operate a real traffic signal. The model has not been evaluated against real Sony World geometry, measured flows, pedestrian phases, public-transport priority, legal requirements, fault modes, or safety certification.

## Reproduce

Python 3.9+ is sufficient. There are no third-party Python dependencies.

```sh
cd experiments/jev-traffic
python3 -m unittest -v test_simulator.py

# Local baselines only
python3 run_experiment.py --baselines-only --replicates 3 --output-dir results-local

# Full experiment; keep the key in the environment, never in this directory
OPENROUTER_API_KEY=... \
  python3 run_experiment.py --replicates 3 --workers 12 --output-dir results-live

python3 analyze_results.py results-live

# Rebuild the replay fragment after changing results or its template
python3 build_visual.py results-r3 visual-template.html replay-fragment.html
```

## View and record locally

The interactive page replays bundled results and needs no API key:

```sh
cd experiments/jev-traffic
python3 -m http.server 8000 --bind 127.0.0.1
```

Open [http://localhost:8000/](http://localhost:8000/) in a browser. Choose a scenario, controller, and arrival seed, move the time slider to the start, then press **Play**. The recording layout is designed to fit at **1280×720 or larger**. Use a 16:9 browser window, hide bookmarks, and record the browser tab rather than the whole desktop. Narrow windows intentionally switch to a stacked mobile layout.

Important files:

- [`sony_signal_sim.py`](sony_signal_sim.py): simulator, safety envelope, controllers, and Jev client.
- [`run_experiment.py`](run_experiment.py): replicated experiment runner.
- [`analyze_results.py`](analyze_results.py): aggregate JSON/CSV generation.
- [`build_visual.py`](build_visual.py): embed saved results in the replay template.
- [`visual-template.html`](visual-template.html): editable replay interface.
- [`test_simulator.py`](test_simulator.py): deterministic and safety tests.
- [`results-r3/aggregate.json`](results-r3/aggregate.json): summarized results.
- [`results-r3/summary.json`](results-r3/summary.json): all 36 run summaries and Jev decisions.
- [`post.md`](post.md): evidence-based LinkedIn draft.
