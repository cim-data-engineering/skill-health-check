"""Edge cases for the run hours rules in references/run-hours/run-hours-signals.md.

Run: python3 -m unittest discover -s tests   (from the repo root; standard library only)
"""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "references" / "run-hours" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import runhours_build as B  # noqa: E402
import runhours_plan as P   # noqa: E402

W = B.WEEK


def series(on_slots, value_on=1.0, value_off=0.0):
    """A reading every 15 minutes: value_on in the given slots, value_off elsewhere."""
    s = set(on_slots)
    return {i: (value_on if i in s else value_off,) * 2 for i in range(W)}


def rec(slots):
    return {"slots": slots, "series": [slots[i][1] for i in sorted(slots)]}


WORKDAYS = [d * 96 + q for d in range(5) for q in range(32, 72)]          # Mon-Fri 08:00-18:00
EVENINGS = [d * 96 + q for d in range(5) for q in range(28, 88)]          # Mon-Fri 07:00-22:00


def unit(*points):
    return {"pull": [dict(p) for p in points], "name": "U"}


def reading(name, fid, slots, role="status"):
    p = {"name": name, "fav_id": fid, "role": role}
    return p, B.read_point(rec(slots), p)


def decide(*pr):
    return B.decide(unit(*[p for p, _ in pr]), {str(p["fav_id"]): r for p, r in pr})


class Decide(unittest.TestCase):
    def test_reading_stuck_off_is_left_out_while_another_changes(self):
        st = reading("Primary Chilled Water Pump Status", 1, series([]))
        sp = reading("Primary Chilled Water Pump Speed", 2, series(WORKDAYS, 80.0), "analog")
        d = decide(st, sp)
        self.assertEqual(d.point["fav_id"], 2)
        self.assertEqual([p["fav_id"] for p in d.left_out], [1])

    def test_status_stuck_on_loses_to_a_moving_speed(self):
        st = reading("Unit Supply Air Fan Status", 1, series(range(W)))
        sp = reading("Unit Supply Air Fan Speed", 2, series(WORKDAYS, 70.0), "analog")
        self.assertEqual(decide(st, sp).point["fav_id"], 2)

    def test_parked_speed_loses_to_the_status(self):
        st = reading("Cooling Tower Fan Status", 1, series(WORKDAYS))
        sp = reading("Cooling Tower Fan Speed", 2, series(EVENINGS, 76.0, 40.0), "analog")   # never below 40%
        self.assertEqual(decide(st, sp).point["fav_id"], 1)

    def test_all_off_all_week_is_drawn_off(self):
        d = decide(reading("Exhaust Air Fan Status", 1, series([])), reading("Exhaust Air Fan Speed", 2, series([]), "analog"))
        self.assertIsNone(d.nodata)
        self.assertTrue(d.flat)
        self.assertEqual(B.ranges(d.reading["on"], True), [])

    def test_all_on_all_week_is_drawn_on_and_unverified(self):
        d = decide(reading("Supply Air Fan Status", 1, series(range(W))), reading("Supply Air Fan Flow Status", 2, series(range(W))))
        self.assertTrue(d.flat)
        self.assertEqual(B.ranges(d.reading["on"], True), [[0, W]])

    def test_flat_and_disagreeing_is_no_reliable_data(self):
        d = decide(reading("Supply Air Fan Status", 1, series(range(W))), reading("Supply Air Fan Flow Status", 2, series([])))
        self.assertIsNotNone(d.nodata)

    def test_boiler_status_stuck_on_is_drawn_from_its_leaving_temperature(self):
        st = reading("Hot Water Boiler Status", 1, series(range(W)))
        t = reading("Hot Water Common Leaving Temperature", 2, series(EVENINGS, 60.0, 20.0), "temp")
        self.assertEqual(decide(st, t).point["fav_id"], 2)

    def test_boiler_status_stuck_off_stays_off_although_the_loop_temperature_moves(self):
        st = reading("Hot Water Boiler Status", 1, series([]))
        t = reading("Hot Water Leaving Temperature", 2, series(EVENINGS, 60.0, 20.0), "temp")
        d = decide(st, t)
        self.assertEqual(d.point["fav_id"], 1)
        self.assertEqual(d.left_out, [])
        self.assertEqual(B.ranges(d.reading["on"], True), [])

    def test_a_temperature_alone_is_never_drawn(self):
        t = reading("Hot Water Common Leaving Temperature", 2, series(EVENINGS, 60.0, 20.0), "temp")
        self.assertIsNotNone(decide(t).nodata)

    def test_fewest_running_hours_wins_between_two_moving_readings(self):
        st = reading("Primary Hot Water Pump Status", 1, series(range(0, W - 96)))      # on all but Sunday
        fl = reading("Primary Hot Water Pump Flow Status", 2, series(EVENINGS))
        self.assertEqual(decide(st, fl).point["fav_id"], 2)

    def test_return_fan_is_ignored_while_the_supply_fan_changes(self):
        sup = reading("Unit Supply Air Fan Status", 1, series(EVENINGS))
        ret = reading("Unit Return Air Fan Status", 2, series(WORKDAYS))           # stops while the supply runs
        ret[0]["fallback"] = True
        self.assertEqual(decide(sup, ret).point["fav_id"], 1)

    def test_return_fan_draws_the_row_when_the_supply_fan_is_stuck_off(self):
        sup = reading("Unit Supply Air Fan Status", 1, series([]))
        ret = reading("Unit Return Air Fan Status", 2, series(WORKDAYS))
        ret[0]["fallback"] = True
        d = decide(sup, ret)
        self.assertEqual(d.point["fav_id"], 2)
        self.assertEqual([p["fav_id"] for p in d.left_out], [1])

    def test_return_fan_alone_draws_the_row(self):
        ret = reading("Unit Return Air Fan Speed", 2, series(WORKDAYS, 60.0), "analog")
        ret[0]["fallback"] = True
        self.assertEqual(decide(ret).point["fav_id"], 2)


class Temperature(unittest.TestCase):
    def test_celsius_range_under_5_is_not_used(self):
        p = {"name": "Hot Water Leaving Temperature", "fav_id": 1, "role": "temp"}
        self.assertIsNone(B.read_point(rec(series(EVENINGS, 61.0, 57.0)), p))
        self.assertIsNotNone(B.read_point(rec(series(EVENINGS, 63.0, 57.0)), p))

    def test_fahrenheit_needs_9_degrees(self):
        p = {"name": "Hot Water Leaving Temperature (Fahrenheit)", "fav_id": 1, "role": "temp"}
        self.assertIsNone(B.read_point(rec(series(EVENINGS, 140.0, 132.0)), p))       # 8 °F
        r = B.read_point(rec(series(EVENINGS, 150.0, 120.0)), p)
        self.assertEqual(r["hours"], len(EVENINGS) / 4)

    def test_upper_half_of_the_range_counts_as_running(self):
        p = {"name": "Hot Water Leaving Temperature", "fav_id": 1, "role": "temp"}
        r = B.read_point(rec(series(WORKDAYS, 70.0, 30.0)), p)
        self.assertEqual(r["hours"], len(WORKDAYS) / 4)


class Plan(unittest.TestCase):
    rules = P.Rules()

    def test_unit_suffixes_are_the_same_metadata(self):
        for name in ("Hot Water Leaving Temperature (Fahrenheit)", "Supply Air Fan Speed (Hz)", "VSD Speed %"):
            self.assertIsNotNone(self.rules.classify(name, "HWB", "SAF", "CWP"), name)

    def test_speed_state_is_a_status(self):
        role, _, state = self.rules.classify("Unit Supply Air Fan Speed (MSV)", "AHU")
        self.assertEqual((role, state), ("status", True))

    def test_enables_and_unlisted_metadata_are_not_fetched(self):
        for name in ("Unit Supply Air Fan Enable", "Chiller Lockout Status", "PAC Compressor Status", "Chiller Compressor Current",
                     "Compressor Status"):
            self.assertIsNone(self.rules.classify(name, "AHU", "CH", "PAC"), name)

    def test_fallback_metadata_is_fetched_and_marked(self):
        u = {"equipment_id": 1, "name": "AHU-1", "peak_type": "AHU", "type": "AHU",
             "points": [{"fav_id": f, "metadata": {"name": n}, "history_available": True}
                        for f, n in ((10, "Unit Return Air Fan Status"), (11, "Unit Supply Air Fan Status"))]}
        P.pick_points(u, self.rules)
        self.assertEqual([(p["fav_id"], p.get("fallback", False)) for p in u["pull"]], [(11, False), (10, True)])
        for name, code in (("Calorifier Domestic Hot Water Pump Status", "CAL"), ("Unit Heater Fan Output", "UH")):
            self.assertGreaterEqual(self.rules.classify(name, code)[1][0], P.FALLBACK_RANK, name)

    def test_fcu_in_the_name_is_a_fan_coil(self):
        self.assertEqual(self.rules.charted_type("B2 FCU 210-1", "AHU"), "FCU")
        self.assertEqual(self.rules.charted_type("AHU-01", "AHU"), "AHU")

    def test_runs_around_the_clock_matches_hyphens_and_underscores(self):
        for zone in ("Data-Center", "Data_Center", "data  centre", "L2 Comms Room"):
            u = {"peak_type": "PAC", "type": "PAC", "name": "CRAC-01", "zone": zone}
            self.assertTrue(self.rules.runs_around_the_clock(u), zone)
        u = {"peak_type": "PAC", "type": "PAC", "name": "PAC-01", "zone": "Database Office"}
        self.assertFalse(self.rules.runs_around_the_clock(u))

    def _unit(self, eid, name, points):
        u = {"equipment_id": eid, "name": name, "peak_type": "HWB", "type": "HWB",
             "points": [{"fav_id": f, "metadata": {"name": n}, "history_available": True} for f, n in points]}
        P.pick_points(u, self.rules)
        return u

    def test_shared_common_temperature_joins_units_with_a_reading(self):
        common = self._unit(1, "TOWER MCC 1 Common-HWB", [(10, "Hot Water Common Leaving Temperature")])
        boiler = self._unit(2, "HWB-1", [(20, "Hot Water Boiler Status")])
        enable_only = self._unit(3, "BOILER-01", [(30, "Hot Water Boiler Enable")])
        P.borrow_shared_temperature([common, boiler, enable_only])
        self.assertEqual(common["pull"], [])
        self.assertEqual(common["why"], "shared record")
        self.assertEqual([p["fav_id"] for p in boiler["pull"]], [20, 10])
        self.assertEqual(boiler["pull"][1]["equipment_id"], 1)
        self.assertEqual(enable_only["pull"], [])
        self.assertEqual(enable_only["why"], "command only")

    def test_link_puts_a_shared_temperature_under_its_own_record(self):
        window = {"link_host": "https://ace.cimenviro.com", "link_start": "2026-11-02T00:00:00.000", "link_end": "2026-11-09T00:00:00.000"}
        href = B.chart_link(window, {"equipment_id": 2}, [20, (1, 10)])
        self.assertTrue(href.endswith("&fav-2=20&fav-1=10"), href)


if __name__ == "__main__":
    unittest.main()
