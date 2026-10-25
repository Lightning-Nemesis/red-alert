"""Load and check what Cubbie hands over: course models (from the syllabus) and the state file.

Formats are described in references/course-model.md and references/state-format.md. Times are ISO 8601; the
state's `now` carries the student's UTC offset, because the sandbox clock may be in another time zone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Optional

WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
SCHEMES = {"weighted", "points"}
PREP_WINDOW_HOURS = 48
DEFAULT_PREFS = {
    "sleep_start": "23:30",
    "sleep_hours": 7.5,
    "daily_cap_hours": 6,
    "buffer_percent": 15,
    "horizon_days": 21,
    "targets": {},
}


class InputError(Exception):
    """The input file is missing, unreadable or malformed (exit code 2)."""


class CourseModelError(Exception):
    """A course model breaks the rules in references/course-model.md (exit code 4)."""


class MissingCourse(Exception):
    """The state names a course that has no saved course model yet (exit code 3)."""

    def __init__(self, course_ids):
        super().__init__(", ".join(course_ids))
        self.course_ids = course_ids


@dataclass
class Item:
    id: str
    title: str
    kind: str  # graded, exam, attendance, study, prep, todo
    course_id: Optional[str] = None
    group: Optional[str] = None
    type: str = "assignment"
    points: float = 0.0
    due: Optional[datetime] = None
    opens: Optional[datetime] = None
    available_until: Optional[datetime] = None
    start: Optional[datetime] = None  # fixed-time items: exams, classes
    end: Optional[datetime] = None
    estimate_minutes: Optional[float] = None
    progress: float = 0.0
    group_project: bool = False
    must_do: bool = False
    extra_credit: bool = False
    rubric: list = field(default_factory=list)
    prepares_for: list = field(default_factory=list)
    url: Optional[str] = None
    quote: Optional[str] = None
    study_hours: Optional[float] = None  # exams: study that captures most of the gain


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime
    kind: str = "meeting"
    importance: str = "fixed"  # fixed, protected, optional
    prep_minutes: float = 0.0


@dataclass
class Course:
    model: dict
    graded: list  # [{"item_id", "group", "score", "out_of"}]
    current_percent: Optional[float] = None
    late_days_left: Optional[int] = None
    target: Optional[str] = None

    @property
    def id(self) -> str:
        return self.model["course_id"]

    @property
    def name(self) -> str:
        return self.model.get("name") or self.id

    @property
    def groups(self) -> dict:
        return {g["id"]: g for g in self.model["groups"]}

    def cutoffs(self) -> list:
        """[(letter, min_percent)], highest first."""
        cuts = self.model.get("cutoffs") or {"A": 93, "A-": 90, "B+": 87, "B": 83, "B-": 80, "C+": 77, "C": 73,
                                             "C-": 70, "D": 60}
        return sorted(((k, float(v)) for k, v in cuts.items()), key=lambda kv: -kv[1])

    def pass_percent(self) -> float:
        if self.model.get("pass_percent") is not None:
            return float(self.model["pass_percent"])
        cuts = self.cutoffs()
        return cuts[-1][1] if cuts else 60.0


@dataclass
class State:
    now: datetime
    tz: tzinfo
    prefs: dict
    courses: dict  # course_id -> Course
    items: list
    events: list
    busy: list  # [(start, end, title)]
    assumptions: list = field(default_factory=list)

    @property
    def horizon_end(self) -> datetime:
        return self.now + timedelta(days=float(self.prefs["horizon_days"]))


def read_json(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise InputError(f"Input file not found: {path}")
    except (OSError, ValueError) as exc:
        raise InputError(f"Input file {path} is not valid JSON: {exc}")


def parse_time(value, tz: tzinfo, label: str) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise InputError(f"{label}: '{value}' is not an ISO 8601 time like 2026-11-02T23:59:00-05:00")
    if tz is None:
        return parsed
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def local_tz(now: datetime, name: Optional[str]) -> tzinfo:
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:  # no tz database in this sandbox: fall back to the offset in `now`
            pass
    return now.tzinfo


# ---------------------------------------------------------------- course models


def validate_course(model: dict) -> tuple:
    """Return (errors, warnings) for a course model; errors make it unusable."""
    errors, warnings = [], []
    if not model.get("course_id"):
        errors.append("course_id is missing")
    scheme = model.get("scheme", "weighted")
    if scheme not in SCHEMES:
        errors.append(f"scheme must be 'weighted' or 'points', not '{scheme}'")
    groups = model.get("groups") or []
    if not groups:
        errors.append("groups is empty: list the grade components from the syllabus")
    ids = [g.get("id") for g in groups]
    if len(set(ids)) != len(ids) or None in ids:
        errors.append("every group needs a unique id")
    known = set(ids)
    if scheme == "weighted" and groups:
        total = sum(float(g.get("weight") or 0) for g in groups if not g.get("extra_credit"))
        if abs(total - 100) > 0.5:
            errors.append(f"group weights add up to {total:g}%, not 100%")
    for g in groups:
        if int(g.get("drop_lowest") or 0) < 0:
            errors.append(f"group {g.get('id')}: drop_lowest can't be negative")
        if g.get("count") is not None and int(g["count"]) < 0:
            errors.append(f"group {g.get('id')}: count can't be negative")
        if not g.get("quote"):
            warnings.append(f"group {g.get('id')}: no syllabus quote for its weight")
        if g.get("count") is None:
            warnings.append(f"group {g.get('id')}: no item count, so values use only the items known so far")
    cuts = model.get("cutoffs")
    if cuts is not None:
        try:
            values = [float(v) for v in cuts.values()]
        except (TypeError, ValueError, AttributeError):
            errors.append("cutoffs must map letters to minimum percentages")
        else:
            if len(set(values)) != len(values):
                errors.append("two letters share the same cutoff")
        if not model.get("cutoffs_quote"):
            warnings.append("cutoffs: no syllabus quote")
    else:
        warnings.append("no letter cutoffs in the syllabus: using the usual scale (A 93, A- 90, B+ 87 ...)")
    for section, key in (("participation", "group"), ("gates", "group"), ("exams", "group")):
        for rule in model.get(section) or []:
            if rule.get(key) not in known:
                errors.append(f"{section}: unknown group '{rule.get(key)}'")
            if not rule.get("quote"):
                warnings.append(f"{section} {rule.get('id') or rule.get(key)}: no syllabus quote")
    for rule in model.get("replacement") or []:
        if rule.get("from") not in known or rule.get("to") not in known:
            errors.append(f"replacement: unknown group in {rule}")
        if not rule.get("quote"):
            warnings.append("replacement rule: no syllabus quote")
    for rule in model.get("participation") or []:
        for day in rule.get("days") or []:
            if day not in WEEKDAYS:
                errors.append(f"participation {rule.get('id')}: day '{day}' must be one of {' '.join(WEEKDAYS)}")
    late = model.get("late_policy") or {}
    if late and not late.get("quote"):
        warnings.append("late_policy: no syllabus quote")
    for question in model.get("ambiguities") or []:
        warnings.append(f"ask the student: {question}")
    return errors, warnings


def check_course(model: dict) -> list:
    errors, warnings = validate_course(model)
    if errors:
        raise CourseModelError(f"{model.get('course_id') or 'course'}: " + "; ".join(errors))
    return warnings


# ---------------------------------------------------------------- state


def _flag(value) -> bool:
    return bool(value) and str(value).lower() not in ("false", "0", "no")


def _num(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InputError(f"'{value}' should be a number")


def load_state(raw: dict, models: dict) -> State:
    """Build the State from the state file and the course models (course_id -> dict)."""
    if not raw.get("now"):
        raise InputError("state.now is missing: pass the student's local date and time with its UTC offset")
    now = parse_time(raw["now"], None, "now")
    if now.tzinfo is None:
        raise InputError("state.now needs a UTC offset, like 2026-11-02T22:40:00-05:00")
    tz = local_tz(now, raw.get("timezone"))
    now = now.astimezone(tz)
    prefs = dict(DEFAULT_PREFS)
    prefs.update({k: v for k, v in (raw.get("preferences") or {}).items() if v is not None})
    targets = prefs.get("targets") or {}

    courses = {}
    missing = []
    for entry in raw.get("courses") or []:
        cid = entry.get("course_id")
        if not cid:
            raise InputError("every entry in courses needs a course_id")
        model = models.get(cid)
        if model is None:
            missing.append(cid)
            continue
        check_course(model)
        late_left = entry.get("late_days_left")
        courses[cid] = Course(
            model=model,
            graded=[
                {"item_id": g.get("item_id"), "group": g.get("group"), "score": _num(g.get("score"), 0.0),
                 "out_of": _num(g.get("out_of"), 0.0)}
                for g in entry.get("graded") or []
            ],
            current_percent=_num(entry.get("current_percent")),
            late_days_left=int(late_left) if late_left is not None else None,
            target=targets.get(cid),
        )
    if missing:
        raise MissingCourse(missing)

    state = State(now=now, tz=tz, prefs=prefs, courses=courses, items=[], events=[], busy=[])
    graded_ids = {g["item_id"] for c in courses.values() for g in c.graded if g.get("item_id")}

    for raw_item in raw.get("items") or []:
        item = _item(raw_item, state)
        if item is None or item.id in graded_ids:
            continue
        state.items.append(item)
    seen = {i.id for i in state.items}

    exam_updates = {e.get("id"): e for e in raw.get("exams") or []}
    for course in courses.values():
        for exam in course.model.get("exams") or []:
            merged = dict(exam)
            merged.update(exam_updates.pop(exam.get("id"), {}) or {})
            merged["course_id"] = course.id
            item = _exam(merged, state)
            if item and item.id not in seen and item.id not in graded_ids:
                state.items.append(item)
                seen.add(item.id)
        for occurrence in _expand_participation(course, state):
            if occurrence.id not in seen and occurrence.id not in graded_ids:
                state.items.append(occurrence)
                seen.add(occurrence.id)
    for extra in exam_updates.values():  # exams Cubbie found that the syllabus didn't list
        if extra.get("course_id") in courses:
            item = _exam(extra, state)
            if item and item.id not in seen:
                state.items.append(item)
                seen.add(item.id)

    for i, raw_event in enumerate(raw.get("events") or []):
        start = parse_time(raw_event.get("start"), tz, "event start")
        end = parse_time(raw_event.get("end"), tz, "event end") or (start + timedelta(hours=1) if start else None)
        if start is None or end <= now:
            continue
        state.events.append(Event(
            id=str(raw_event.get("id") or f"event{i}"), title=raw_event.get("title") or "Event", start=start,
            end=end, kind=raw_event.get("kind") or "meeting", importance=raw_event.get("importance") or "fixed",
            prep_minutes=_num(raw_event.get("prep_minutes"), 0.0),
        ))
    for block in raw.get("busy") or []:
        start = parse_time(block.get("start"), tz, "busy start")
        end = parse_time(block.get("end"), tz, "busy end")
        if start and end and end > now:
            state.busy.append((start, end, block.get("title") or "Busy"))

    for i, todo in enumerate(raw.get("todos") or []):
        if _flag(todo.get("done")):
            continue
        state.items.append(Item(
            id=str(todo.get("id") or f"todo{i}"), title=todo.get("title") or "To-do", kind="todo", type="todo",
            due=parse_time(todo.get("due"), tz, "todo due"), estimate_minutes=_num(todo.get("estimate_minutes")),
            must_do=_flag(todo.get("must_do")),
        ))
    for event in state.events:
        if event.prep_minutes > 0 and event.start > now:
            state.items.append(Item(
                id=f"prep:{event.id}", title=f"Prep: {event.title}", kind="prep", type="prep", due=event.start,
                opens=max(now, event.start - timedelta(hours=PREP_WINDOW_HOURS)),  # prep close to the event
                estimate_minutes=event.prep_minutes, must_do=True,
            ))
    return state


def _item(raw: dict, state: State) -> Optional[Item]:
    if _flag(raw.get("submitted")):
        return None
    if not raw.get("id"):
        raise InputError(f"an item has no id: {raw.get('title')}")
    tz = state.tz
    if (raw.get("type") or "") == "exam":
        return _exam(raw, state)
    course_id = raw.get("course_id")
    if course_id and course_id not in state.courses:
        raise InputError(f"item {raw['id']} names course '{course_id}', which is not in courses")
    group = raw.get("group")
    if course_id and group not in state.courses[course_id].groups:
        raise InputError(f"item {raw['id']}: group '{group}' is not in the {course_id} course model")
    due = parse_time(raw.get("due"), tz, f"item {raw['id']} due")
    start = parse_time(raw.get("start"), tz, f"item {raw['id']} start")
    if start and start <= state.now:
        return None
    kind = "todo"
    if course_id:
        kind = "attendance" if start else "graded"  # fixed-time graded items: classes, labs, sections
    item = Item(
        id=str(raw["id"]), title=raw.get("title") or raw["id"], kind=kind,
        course_id=course_id, group=group, type=raw.get("type") or "assignment", points=_num(raw.get("points"), 0.0),
        due=due, opens=parse_time(raw.get("opens"), tz, f"item {raw['id']} opens"),
        available_until=parse_time(raw.get("available_until"), tz, f"item {raw['id']} available_until"),
        start=start, end=parse_time(raw.get("end"), tz, f"item {raw['id']} end"),
        estimate_minutes=_num(raw.get("estimate_minutes")),
        progress=min(max(_num(raw.get("progress"), 0.0), 0.0), 0.95),
        group_project=_flag(raw.get("group_project")), must_do=_flag(raw.get("must_do")),
        extra_credit=_flag(raw.get("extra_credit")), rubric=raw.get("rubric") or [],
        prepares_for=raw.get("prepares_for") or [], url=raw.get("url"),
    )
    if item.start and not item.end:
        item.end = item.start + timedelta(hours=1)
    if item.due and item.due <= state.now:
        # Past due but Canvas still accepts it: only a late submission is left.
        if not item.available_until or item.available_until <= state.now:
            return None
    return item


def _exam(raw: dict, state: State) -> Optional[Item]:
    start = parse_time(raw.get("at") or raw.get("start"), state.tz, f"exam {raw.get('id')}")
    if start is None or start <= state.now or start > state.horizon_end:
        return None
    course = state.courses.get(raw.get("course_id"))
    if course is None:
        return None
    if raw.get("group") not in course.groups:
        raise InputError(f"exam {raw.get('id')}: group '{raw.get('group')}' is not in the {course.id} course model")
    minutes = _num(raw.get("minutes"), 90.0)
    return Item(
        id=str(raw.get("id")), title=raw.get("title") or raw.get("name") or "Exam", kind="exam", type="exam",
        course_id=course.id, group=raw.get("group"), points=_num(raw.get("points"), 100.0), due=start,
        start=start, end=start + timedelta(minutes=minutes), must_do=True, quote=raw.get("quote"),
        study_hours=_num(raw.get("study_hours")),
    )


def _expand_participation(course: Course, state: State) -> list:
    out = []
    for rule in course.model.get("participation") or []:
        days = rule.get("days") or []
        if not days or not rule.get("start"):
            continue
        hh, mm = (int(x) for x in str(rule["start"]).split(":")[:2])
        minutes = _num(rule.get("minutes"), 60.0)
        day = state.now.date()
        while datetime.combine(day, time(0), tzinfo=state.tz) < state.horizon_end:
            if WEEKDAYS[day.weekday()] in days:
                start = datetime.combine(day, time(hh, mm), tzinfo=state.tz)
                if state.now < start < state.horizon_end:
                    out.append(Item(
                        id=f"{rule.get('id') or 'class'}@{day.isoformat()}",
                        title=f"{rule.get('title') or 'Class'} ({_short_date(day)})", kind="attendance",
                        type="attendance", course_id=course.id, group=rule.get("group"),
                        points=_num(rule.get("points_each"), 1.0), due=start + timedelta(minutes=minutes),
                        start=start, end=start + timedelta(minutes=minutes), estimate_minutes=minutes,
                        quote=rule.get("quote"),
                    ))
            day += timedelta(days=1)
    return out


def _short_date(day: date) -> str:
    return day.strftime("%a %b ") + str(day.day)
