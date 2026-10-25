"""Saved state under HOME: confirmed course models, the effort log and the current plan.

Everything lives in ~/.config/red-alert/ (HOME survives sandbox restarts and Skill updates). SKILL_DATA_DIR
overrides the folder, which the tests use to keep the real state untouched. Sample runs never call these.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


class StoreError(Exception):
    """Saved state exists but can't be read."""


def data_dir() -> Path:
    # SKILL_DATA_DIR is where Skills installed before folders kept their data.
    return Path(os.environ.get("SKILL_DATA_DIR") or Path.home() / ".config" / "red-alert")


def _read(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StoreError(f"{path} is unreadable: {exc}") from exc


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def course_path(course_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in course_id)
    return data_dir() / "courses" / f"{safe}.json"


def load_course(course_id: str):
    return _read(course_path(course_id), None)


def save_course(model: dict) -> Path:
    path = course_path(model["course_id"])
    _write(path, model)
    return path


def load_effort() -> dict:
    return _read(data_dir() / "effort.json", {"entries": []})


def save_effort(log: dict) -> None:
    _write(data_dir() / "effort.json", log)


def load_plan():
    return _read(data_dir() / "plan.json", None)


def save_plan(plan: dict) -> None:
    _write(data_dir() / "plan.json", plan)


def default_plan_md() -> Path:
    return data_dir() / "plan.md"
