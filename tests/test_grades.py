import unittest

from helpers import build, course, state

from redalert_core.grades import course_percent, gates_failed, target_cutoff
from redalert_core.model import CourseModelError, InputError, check_course, validate_course


def graded(group, score, out_of, item_id=None):
    return {"item_id": item_id, "group": group, "score": score, "out_of": out_of}


class WeightedAndPoints(unittest.TestCase):
    def test_weighted_groups(self):
        m = course(groups=[{"id": "hw", "weight": 40, "quote": "q"}, {"id": "exam", "weight": 60, "quote": "q"}])
        st = build([m], state([m], graded={"c1": [graded("hw", 8, 10), graded("exam", 90, 100)]}))
        self.assertAlmostEqual(course_percent(st.courses["c1"], [], {}), 0.4 * 80 + 0.6 * 90)

    def test_total_points(self):
        m = course(scheme="points", groups=[{"id": "hw", "quote": "q"}, {"id": "exam", "quote": "q"}])
        st = build([m], state([m], graded={"c1": [graded("hw", 8, 10), graded("exam", 90, 100)]}))
        self.assertAlmostEqual(course_percent(st.courses["c1"], [], {}), 100 * 98 / 110)

    def test_placeholders_fill_the_rest_of_the_term(self):
        # 4 homeworks expected, 1 graded at 90%: the other 3 are assumed at the same 90%.
        m = course()
        st = build([m], state([m], graded={"c1": [graded("hw", 9, 10), graded("exam", 80, 100)]}))
        self.assertAlmostEqual(course_percent(st.courses["c1"], [], {}), 0.5 * 90 + 0.5 * 80)


class FinePrint(unittest.TestCase):
    def test_skipping_the_item_that_gets_dropped_costs_almost_nothing(self):
        m = course(groups=[{"id": "hw", "weight": 100, "count": 4, "drop_lowest": 1, "quote": "q"}])
        items = [{"id": "hw4", "course_id": "c1", "group": "hw", "points": 10, "due": "2026-11-04T23:59:00-05:00"}]
        rows = [graded("hw", 9, 10, "hw1"), graded("hw", 9, 10, "hw2"), graded("hw", 9, 10, "hw3")]
        st = build([m], state([m], items, graded={"c1": rows}))
        c = st.courses["c1"]
        done = course_percent(c, st.items, {"hw4": 9})
        skipped = course_percent(c, st.items, {"hw4": 0})
        self.assertAlmostEqual(done, skipped)

    def test_replacement_only_counts_once_the_final_is_graded(self):
        groups = [{"id": "mid", "weight": 50, "count": 2, "quote": "q"},
                  {"id": "final", "weight": 50, "count": 1, "quote": "q"}]
        rule = [{"from": "final", "to": "mid", "quote": "q"}]
        m = course(groups=groups, replacement=rule)
        ungraded = build([m], state([m], graded={"c1": [graded("mid", 60, 100), graded("mid", 90, 100)]}))
        # Final not graded yet: the 60 stays.
        self.assertAlmostEqual(course_percent(ungraded.courses["c1"], [], {}), 0.5 * 75 + 0.5 * 75)
        with_final = build([m], state([m], graded={"c1": [graded("mid", 60, 100), graded("mid", 90, 100),
                                                          graded("final", 85, 100)]}))
        self.assertAlmostEqual(course_percent(with_final.courses["c1"], [], {}), 0.5 * 87.5 + 0.5 * 85)

    def test_gate(self):
        m = course(gates=[{"group": "exam", "min_percent": 60, "quote": "q"}])
        st = build([m], state([m], graded={"c1": [graded("hw", 10, 10), graded("exam", 50, 100)]}))
        self.assertEqual(len(gates_failed(st.courses["c1"], [], {})), 1)

    def test_letter_within_reach_becomes_the_target(self):
        m = course()
        st = build([m], state([m]))
        self.assertEqual(target_cutoff(st.courses["c1"], 86.9), ("B+", 87.0))
        self.assertEqual(target_cutoff(st.courses["c1"], 85.0), ("B", 83.0))


class Validation(unittest.TestCase):
    def test_weights_must_add_up(self):
        m = course(groups=[{"id": "hw", "weight": 40, "quote": "q"}, {"id": "exam", "weight": 50, "quote": "q"}])
        errors, _ = validate_course(m)
        self.assertTrue(any("add up to 90%" in e for e in errors))
        with self.assertRaises(CourseModelError):
            check_course(m)

    def test_missing_quotes_are_warnings(self):
        m = course(groups=[{"id": "hw", "weight": 100}])
        errors, warnings = validate_course(m)
        self.assertEqual(errors, [])
        self.assertTrue(any("no syllabus quote" in w for w in warnings))

    def test_now_needs_an_offset(self):
        m = course()
        raw = state([m])
        raw["now"] = "2026-11-02T20:00:00"
        with self.assertRaises(InputError):
            build([m], raw)


if __name__ == "__main__":
    unittest.main()
