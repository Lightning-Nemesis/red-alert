import unittest
from datetime import datetime, timedelta

from helpers import build, course, state

from redalert_core.timeplan import Calendar


def at(text):
    return datetime.fromisoformat(text)


class Scheduling(unittest.TestCase):
    def setUp(self):
        self.m = course()
        self.state = build([self.m], state([self.m]))
        self.cal = Calendar(self.state)

    def task(self, task_id, minutes, deadline, release=None):
        return {"id": task_id, "minutes": minutes, "deadline": at(deadline), "release": release}

    def test_quick_item_due_tomorrow_gets_a_slot_before_it_is_due(self):
        short, blocks, late = self.cal.schedule([self.task("ed", 15, "2026-11-03T20:00:00-05:00")])
        self.assertEqual(short, 0)
        self.assertEqual(late, [])
        self.assertLessEqual(blocks[0]["end"], at("2026-11-03T20:00:00-05:00"))

    def test_sleep_is_never_used(self):
        _, blocks, _ = self.cal.schedule([self.task("big", 20 * 60, "2026-11-08T23:00:00-05:00")])
        for b in blocks:
            t = b["start"]
            while t < b["end"]:
                self.assertFalse(t.hour >= 23 or t.hour < 7, f"work at {t}")
                t += timedelta(minutes=15)

    def test_daily_cap(self):
        _, blocks, _ = self.cal.schedule([self.task("big", 30 * 60, "2026-11-08T23:00:00-05:00")])
        per_day = {}
        for b in blocks:
            day = (b["start"] - timedelta(hours=7)).date()
            per_day[day] = per_day.get(day, 0) + b["minutes"]
        self.assertTrue(all(m <= 6 * 60 for m in per_day.values()), per_day)

    def test_too_much_work_reports_a_shortfall(self):
        short, _, late = self.cal.schedule([self.task("huge", 30 * 60, "2026-11-04T12:00:00-05:00")])
        self.assertGreater(short, 0)
        self.assertEqual(late, ["huge"])

    def test_busy_blocks_are_respected(self):
        raw = state([self.m], busy=[{"title": "Shift", "start": "2026-11-03T07:00:00-05:00",
                                     "end": "2026-11-03T23:00:00-05:00"}])
        cal = Calendar(build([self.m], raw))
        _, blocks, _ = cal.schedule([self.task("t", 120, "2026-11-04T23:00:00-05:00")])
        for b in blocks:
            self.assertFalse(b["start"].date() == at("2026-11-03T12:00:00-05:00").date() and b["start"].hour >= 7)


if __name__ == "__main__":
    unittest.main()
