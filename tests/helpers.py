"""Small builders for tests: a course model, a state file, and loading them the way the script does."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from redalert_core.model import load_state  # noqa: E402

NOW = "2026-11-02T20:00:00-05:00"  # a Monday evening


def course(course_id="c1", groups=None, **extra) -> dict:
    model = {
        "course_id": course_id, "name": course_id.upper(), "scheme": "weighted",
        "groups": groups or [
            {"id": "hw", "name": "Homework", "weight": 50, "count": 4, "quote": "q"},
            {"id": "exam", "name": "Exam", "weight": 50, "count": 1, "quote": "q"},
        ],
        "cutoffs": {"A": 93, "A-": 90, "B+": 87, "B": 83, "C": 73, "D": 60}, "cutoffs_quote": "q",
    }
    model.update(extra)
    return model


def state(models, items=(), graded=None, **extra) -> dict:
    raw = {
        "now": NOW, "timezone": None,
        "preferences": {"sleep_start": "23:00", "sleep_hours": 8, "daily_cap_hours": 6, "buffer_percent": 0,
                        "horizon_days": 7},
        "courses": [{"course_id": m["course_id"], "graded": (graded or {}).get(m["course_id"], [])} for m in models],
        "items": list(items),
    }
    raw.update(extra)
    return raw


def build(models, raw):
    return load_state(copy.deepcopy(raw), {m["course_id"]: copy.deepcopy(m) for m in models})


def sample():
    assets = ROOT / "assets"
    models = {}
    for path in assets.glob("sample_course_*.json"):
        m = json.loads(path.read_text(encoding="utf-8"))
        models[m["course_id"]] = m
    raw = json.loads((assets / "sample_state.json").read_text(encoding="utf-8"))
    return load_state(raw, models)
