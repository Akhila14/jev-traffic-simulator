import unittest

from sony_signal_sim import (
    EIGHTY_FEET,
    INNER_RING,
    MIN_GREEN_SECONDS,
    Decision,
    FixedTimeController,
    SCENARIOS,
    Simulator,
    prose_state,
)


class SimulatorTests(unittest.TestCase):
    def test_baseline_is_reproducible(self):
        first, _ = Simulator(SCENARIOS["morning_peak"], FixedTimeController(), 120).run()
        second, _ = Simulator(SCENARIOS["morning_peak"], FixedTimeController(), 120).run()
        self.assertEqual(first, second)

    def test_minimum_green_rejects_early_switch(self):
        sim = Simulator(SCENARIOS["morning_peak"], FixedTimeController(), 20)
        sim.phase = INNER_RING
        sim.green_elapsed = MIN_GREEN_SECONDS - 1
        applied, reason = sim.apply_safety(Decision("serve_80_feet_road"), 10)
        self.assertEqual(applied, INNER_RING)
        self.assertEqual(reason, "minimum_green")

    def test_prose_state_uses_corridor_names_not_raw_schema(self):
        sim = Simulator(SCENARIOS["morning_peak"], FixedTimeController(), 20)
        state = prose_state(sim.snapshot(0))
        self.assertIn("Inner Ring Road", state)
        self.assertIn("Koramangala 80 Feet Road", state)
        self.assertNotIn("queue_vehicles", state)

    def test_trace_is_downsampled(self):
        _, trace = Simulator(SCENARIOS["morning_peak"], FixedTimeController(), 60).run()
        self.assertEqual(len(trace), 12)


if __name__ == "__main__":
    unittest.main()
