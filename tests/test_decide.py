import unittest
from datetime import timedelta

from helpers import build, course, sample, state

from redalert_core import report
from redalert_core.decide import make_plan

DUE_TOMORROW = "2026-11-03T20:00:00-05:00"
DUE_WED = "2026-11-04T23:59:00-05:00"


def verdicts(plan) -> dict:
    return {d.item.id: d for d in plan.decisions}


def tight(raw, hours_per_day):
    raw["preferences"]["daily_cap_hours"] = hours_per_day
    return raw


class UsersExample(unittest.TestCase):
    """The student's own example: a 15-minute post worth 1 point vs a day-long assignment worth 0.5 points."""

    def setUp(self):
        groups = [
            {"id": "ed", "name": "Ed posts", "weight": 10, "count": 10, "quote": "1% per post"},
            {"id": "attend", "name": "Attendance", "weight": 5, "count": 25, "quote": "0.2% per lecture"},
            {"id": "hw", "name": "Homework", "weight": 4, "count": 8, "quote": "0.5% each"},
            {"id": "mid", "name": "Midterm", "weight": 41, "count": 1, "quote": "q"},
            {"id": "final", "name": "Final", "weight": 40, "count": 1, "quote": "q"},
        ]
        self.m = course(groups=groups, participation=[
            {"id": "lec", "title": "C1 lecture", "group": "attend", "days": ["TU"], "start": "14:00", "minutes": 60,
             "quote": "q"}], exams=[{"id": "mid1", "title": "Midterm", "group": "mid", "points": 100,
                                     "at": "2026-11-07T10:00:00-05:00", "quote": "q"}])
        items = [
            {"id": "post", "course_id": "c1", "group": "ed", "title": "Ed post", "type": "discussion", "points": 1,
             "due": DUE_TOMORROW, "estimate_minutes": 15},
            {"id": "hw", "course_id": "c1", "group": "hw", "title": "Day-long assignment", "points": 10,
             "due": DUE_WED, "estimate_minutes": 480},
        ]
        graded = {"c1": [{"group": "ed", "score": 1, "out_of": 1}, {"group": "hw", "score": 9, "out_of": 10},
                         {"group": "attend", "score": 1, "out_of": 1}]}
        # 2 h a day: the 8 h assignment can't fit before Wednesday next to the post, the lecture and studying.
        self.plan = make_plan(build([self.m], tight(state([self.m], items, graded), 2)), {"entries": []})
        self.v = verdicts(self.plan)

    def test_post_is_done_first(self):
        self.assertEqual(self.v["post"].verdict, "DO")
        label, nxt = report.tonight(self.plan)
        self.assertEqual(nxt[0][1].item.id, "post")

    def test_post_is_worth_about_one_point(self):
        self.assertAlmostEqual(self.v["post"].value, 1.0, delta=0.05)

    def test_day_long_assignment_is_cut(self):
        self.assertIn(self.v["hw"].verdict, ("SHRINK", "SKIP"))
        self.assertAlmostEqual(self.v["hw"].full_value, 0.45, delta=0.1)

    def test_tuesday_lecture_is_attended(self):
        self.assertEqual(self.v["lec@2026-11-03"].verdict, "DO")

    def test_midterm_gets_study_time(self):
        self.assertGreater(self.v["study:mid1"].minutes, 0)

    def test_reasons_carry_the_numbers(self):
        self.assertIn("15 min", report.reason(self.plan, self.v["post"]))
        self.assertIn("pt", report.reason(self.plan, self.v["hw"]))


class Rules(unittest.TestCase):
    def two_courses(self, grade_a, grade_b, hours):
        groups = [{"id": "hw", "name": "Homework", "weight": 100, "count": 5, "quote": "q"}]
        ma, mb = course("near", groups=groups), course("safe", groups=groups)
        items = [
            {"id": f"{cid}_hw", "course_id": cid, "group": "hw", "title": f"{cid} homework", "points": 10,
             "due": DUE_TOMORROW, "estimate_minutes": 180} for cid in ("near", "safe")
        ]
        graded = {"near": [{"group": "hw", "score": grade_a, "out_of": 10} for _ in range(4)],
                  "safe": [{"group": "hw", "score": grade_b, "out_of": 10} for _ in range(4)]}
        raw = tight(state([ma, mb], items, graded), hours)
        return verdicts(make_plan(build([ma, mb], raw), {"entries": []}))

    def test_points_near_a_cutoff_count_more(self):
        v = self.two_courses(8.75, 9.9, 1.5)  # room for one; 87.5 sits on the B+ line, 99 is safe
        self.assertGreater(v["near_hw"].minutes, v["safe_hw"].minutes)
        self.assertGreater(v["near_hw"].multiplier, v["safe_hw"].multiplier)

    def test_course_at_risk_of_failing_is_never_skipped(self):
        groups = [{"id": "hw", "name": "Homework", "weight": 100, "count": 5, "quote": "q"}]
        m = course(groups=groups)
        items = [{"id": f"hw{n}", "course_id": "c1", "group": "hw", "title": f"HW {n}", "points": 10,
                  "due": DUE_WED, "estimate_minutes": 300} for n in range(2)]
        graded = {"c1": [{"group": "hw", "score": 6, "out_of": 10} for _ in range(3)]}
        v = verdicts(make_plan(build([m], tight(state([m], items, graded), 2)), {"entries": []}))
        self.assertTrue(all(d.verdict != "SKIP" for d in v.values() if d.item.kind == "graded"))

    def test_late_penalty_beats_skipping(self):
        m = course(late_policy={"accepts_late": True, "penalty_per_day": 10, "max_days": 3, "quote": "q"})
        items = [{"id": "big", "course_id": "c1", "group": "hw", "title": "Big HW", "points": 100,
                  "due": "2026-11-03T12:00:00-05:00", "estimate_minutes": 600}]
        v = verdicts(make_plan(build([m], tight(state([m], items), 4)), {"entries": []}))
        self.assertEqual(v["big"].verdict, "SHIFT")

    def test_group_project_is_never_skipped(self):
        m = course()
        items = [{"id": "proj", "course_id": "c1", "group": "hw", "title": "Group project", "points": 10,
                  "due": DUE_WED, "estimate_minutes": 120, "group_project": True}]
        v = verdicts(make_plan(build([m], tight(state([m], items), 1)), {"entries": []}))
        self.assertEqual(v["proj"].verdict, "DO")
        self.assertEqual(v["proj"].notes.get("must"), "group_project")

    def test_logged_effort_changes_estimates(self):
        m = course()
        items = [{"id": "hw2", "course_id": "c1", "group": "hw", "title": "HW 2", "type": "problem_set",
                  "points": 10, "due": DUE_WED}]
        log = {"entries": [{"item_id": f"old{n}", "course_id": "c1", "type": "problem_set",
                            "estimate_minutes": 240, "minutes": 480, "done": True} for n in range(4)]}
        plan = make_plan(build([m], state([m], items)), log)
        self.assertGreater(verdicts(plan)["hw2"].full_minutes, 240 * 1.4)
        self.assertTrue(any("underestimate" in line for line in plan.insights))


class Sample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = make_plan(sample(), {"entries": []})
        cls.v = verdicts(cls.plan)

    def test_it_is_a_red_alert(self):
        self.assertTrue(report.is_alert(self.plan))
        self.assertTrue(report.headline(self.plan).startswith("RED ALERT"))

    def test_low_value_dropped_problem_set_is_skipped(self):
        self.assertEqual(self.v["ps6"].verdict, "SKIP")
        self.assertIn("dropped", report.reason(self.plan, self.v["ps6"]))

    def test_interview_is_protected_and_prepped_close_to_it(self):
        interview = next(e for e in self.plan.state.events if e.id == "stripe")
        prep = [b for b in self.plan.blocks if b["id"] == "prep:stripe"]
        self.assertTrue(prep)
        for b in prep:
            self.assertLessEqual(b["end"], interview.start)
            self.assertGreaterEqual(b["start"], interview.start - timedelta(hours=48))
        for b in self.plan.blocks:
            if not b.get("fixed"):
                self.assertFalse(b["start"] < interview.end and interview.start < b["end"], b)

    def test_lecture_that_clashes_with_the_career_fair_is_skipped(self):
        self.assertEqual(self.v["cs_lecture@2026-11-10"].verdict, "SKIP")
        self.assertIn("Career fair", report.reason(self.plan, self.v["cs_lecture@2026-11-10"]))

    def test_every_exam_gets_study_time(self):
        for exam_id in ("cs_mid", "econ_mid2", "psyc_exam2"):
            self.assertGreater(self.v[f"study:{exam_id}"].minutes, 0, exam_id)

    def test_group_project_kept(self):
        self.assertEqual(self.v["m2"].verdict, "DO")

    def test_work_finishes_before_deadlines(self):
        self.assertLess(self.plan.shortfall, 1)
        for b in self.plan.blocks:
            d = self.v.get(b["id"])
            if d and not b.get("fixed") and d.option.deadline:
                self.assertLessEqual(b["end"], d.option.deadline, b["id"])

    def test_text_fits_in_what_cubbie_reads(self):
        self.assertLess(len(report.text(self.plan, "plan.md")), 8000)


if __name__ == "__main__":
    unittest.main()
