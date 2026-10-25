import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, course, state

SCRIPT = ROOT / "scripts" / "redalert.py"


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = dict(os.environ, SKILL_DATA_DIR=str(self.tmp / "data"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=self.env,
                              cwd=str(ROOT))

    def write(self, name, data) -> str:
        path = self.tmp / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_sample_plan_runs_and_writes_nothing(self):
        r = self.run_cli("plan", "--sample")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("RED ALERT", r.stdout)
        self.assertFalse((self.tmp / "data").exists())

    def test_every_sample_command(self):
        for args in (["scan", "--sample"], ["course", "--sample"], ["whatif", "--sample", "--skip", "lab3"],
                     ["recap", "--sample"], ["plan", "--sample", "--json"]):
            r = self.run_cli(*args)
            self.assertEqual(r.returncode, 0, (args, r.stderr))

    def test_missing_course_model_exits_3(self):
        m = course()
        r = self.run_cli("plan", "--input", self.write("state.json", state([m])))
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("c1", r.stderr)

    def test_invalid_course_model_exits_4(self):
        m = course(groups=[{"id": "hw", "weight": 60, "quote": "q"}])
        r = self.run_cli("course", "--input", self.write("course.json", m))
        self.assertEqual(r.returncode, 4)

    def test_bad_input_exits_2(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.run_cli("plan", "--input", str(bad)).returncode, 2)
        self.assertEqual(self.run_cli("plan").returncode, 2)

    def test_nothing_due_exits_5(self):
        m = course()
        self.assertEqual(self.run_cli("course", "--input", self.write("c.json", m), "--save").returncode, 0)
        self.assertEqual(self.run_cli("plan", "--input", self.write("s.json", state([m]))).returncode, 5)

    def test_full_cycle_save_plan_log_replan(self):
        m = course()
        r = self.run_cli("course", "--input", self.write("c.json", m))
        self.assertIn("Not saved yet", r.stdout)
        self.assertEqual(self.run_cli("course", "--input", self.write("c.json", m), "--save").returncode, 0)
        items = [{"id": "hw1", "course_id": "c1", "group": "hw", "title": "HW 1", "type": "problem_set",
                  "points": 10, "due": "2026-11-05T23:59:00-05:00", "estimate_minutes": 240}]
        st = self.write("s.json", state([m], items))
        r = self.run_cli("plan", "--input", st)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / "data" / "plan.json").exists())
        self.assertTrue((self.tmp / "data" / "plan.md").exists())
        r = self.run_cli("log", "--item", "hw1", "--minutes", "120")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 h so far", r.stdout)
        r = self.run_cli("plan", "--input", st, "--json")
        data = json.loads(r.stdout)
        self.assertTrue(data["updated_existing_plan"])
        hw = next(d for d in data["decisions"] if d["id"] == "hw1")
        self.assertLessEqual(hw["full_minutes"], 130)
        self.assertEqual(self.run_cli("log", "--item", "hw1", "--minutes", "60", "--done").returncode, 0)
        r = self.run_cli("recap")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("1/1", r.stdout)

    def test_log_unknown_item_exits_2(self):
        self.assertEqual(self.run_cli("log", "--item", "nope", "--minutes", "10").returncode, 2)


if __name__ == "__main__":
    unittest.main()
