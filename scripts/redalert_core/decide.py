"""The decision step: what to do in full, what to shrink, what to shift and what to skip.

Every item gets options (skip, shrink levels, full, late), exams get study in 30-minute steps. Fixed things
(interviews, prep, exams) are placed first and must-do items start at their cheapest acceptable option. Then the
planner keeps applying the upgrade that gains the most grade per hour, as long as everything still fits before
its deadline. Grade value always comes from recomputing the course grade, so drop rules, replacement rules and
gates count without special cases.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from . import effort as effort_mod
from . import exams as exams_mod
from .grades import course_average, course_percent, gates_failed, group_average, letter_for, target_cutoff
from .timeplan import Calendar, collisions

# Tuning knobs, all in one place.
QUICK_WIN_MINUTES = 15
NEAR_CUTOFF = 3.0  # points either side of the protected cutoff where points count more
MAX_BOOST = 3.0  # multiplier right at the cutoff (and when the course is at risk of failing)
SAFE_MARGIN = 5.0  # points above the protected cutoff where a course counts as safe
SAFE_FACTOR = 0.5
FAIL_MARGIN = 5.0  # within this many points of passing, every graded item is must-do
GATE_PENALTY = 50.0
TODO_VALUE_PER_HOUR = 0.1  # to-dos have no grade; they fill time grade work doesn't need
DEFAULT_SHRINK = [(0.6, 0.85), (0.35, 0.65)]  # (share of the effort, share of the score)
LIGHT_EFFORT, LIGHT_CREDIT = 0.25, 0.5  # a rubric part done lightly


@dataclass
class Option:
    kind: str  # skip, shrink, full, late, attend, study, fixed
    minutes: float
    score: float = 0.0  # share of the item's expected score earned
    deadline: Optional[object] = None
    late_days: int = 0
    uses_late_days: bool = False
    light_parts: list = field(default_factory=list)


@dataclass
class Decision:
    item: object
    option: Option
    verdict: str  # DO, SHRINK, SHIFT, SKIP
    value: float  # course percentage points this choice earns vs skipping
    full_value: float  # what doing it in full, on time, would earn vs skipping
    full_minutes: float
    multiplier: float = 1.0
    notes: dict = field(default_factory=dict)

    @property
    def minutes(self) -> float:
        return self.option.minutes


@dataclass
class Plan:
    state: object
    calendar: Calendar
    decisions: list
    blocks: list
    shortfall: float
    projections: dict
    headline: dict
    assumptions: list
    warnings: list
    insights: list
    priors: dict = field(default_factory=dict)  # item id -> estimate before learning, for the effort log


class Planner:
    def __init__(self, state, effort_log: dict, forced: Optional[dict] = None):
        self.state = state
        self.forced = forced or {}
        self.learned = effort_mod.ratios(effort_log)
        self.cal = Calendar(state)
        self.assumptions = []
        self._avg = {}
        self.items = [i for i in state.items if i.kind != "exam" or i.course_id in state.courses]
        self.exams = [i for i in self.items if i.kind == "exam"]
        self.by_id = {i.id: i for i in self.items}
        self.course_items = {cid: [i for i in self.items if i.course_id == cid] for cid in state.courses}
        self.full_minutes, self.prior_minutes = {}, {}
        for item in self.items:
            full, prior, _ = effort_mod.estimate(item, self.learned)
            self.full_minutes[item.id] = full
            self.prior_minutes[item.id] = prior
        self._link_exams()
        self._study_items()
        self.options = {i.id: self._options(i) for i in self.flexible()}
        self._baseline()
        self._floors()

    # ------------------------------------------------------------ setup

    def flexible(self) -> list:
        return [i for i in self.items if i.kind != "exam"]

    def _link_exams(self):
        """Items and classes that prepare for an exam add to its study time."""
        self.links = {e.id: [] for e in self.exams}
        for item in self.items:
            for exam_id in item.prepares_for or []:
                if exam_id in self.links:
                    self.links[exam_id].append(item.id)
        for item in self.items:
            if item.kind != "attendance":
                continue
            for exam in self.exams:
                if exam.course_id == item.course_id and item.start < exam.start:
                    self.links[exam.id].append(item.id)
                    item.prepares_for = list(item.prepares_for) + [exam.id]

    def _study_items(self):
        from .model import Item

        for exam in self.exams:
            study = Item(id=f"study:{exam.id}", title=f"Study for {exam.title}", kind="study", type="study",
                         course_id=exam.course_id, due=exam.start, study_hours=exams_mod.full_study_hours(exam))
            self.items.append(study)
            self.by_id[study.id] = study
            self.full_minutes[study.id] = self.prior_minutes[study.id] = study.study_hours * 60

    def _options(self, item) -> list:
        now = self.state.now
        horizon = self.state.horizon_end
        full = self.full_minutes[item.id]
        remaining = full * (1 - item.progress)
        deadline = min(item.due, horizon) if item.due else horizon
        if item.kind == "study":
            steps = int(math.ceil(full / exams_mod.STEP_MINUTES))
            return [Option("study", k * exams_mod.STEP_MINUTES, deadline=item.due) for k in range(steps + 1)]
        if item.kind == "attendance":
            if self._conflict(item):
                return [Option("skip", 0)]
            return [Option("skip", 0), Option("attend", full, 1.0, deadline=item.end)]
        if item.kind == "prep":
            return [Option("full", remaining, 1.0, deadline=deadline)]
        if item.kind == "todo":
            return [Option("skip", 0), Option("full", remaining, 1.0, deadline=deadline)]
        opts = [Option("skip", 0)]
        on_time = item.due is None or item.due > now
        if on_time and remaining > QUICK_WIN_MINUTES and not item.group_project:
            for effort_share, score_share, light in self._shrink_levels(item):
                opts.append(Option("shrink", remaining * effort_share, score_share, deadline=deadline,
                                   light_parts=light))
        if on_time:
            opts.append(Option("full", remaining, 1.0, deadline=deadline))
        if not item.group_project and item.due:
            opts += self._late_options(item, remaining)
        return opts

    def _conflict(self, item):
        """The fixed or protected event a class overlaps, if any: those come first."""
        for event in self.state.events:
            if event.importance in ("fixed", "protected") and event.start < item.end and item.start < event.end:
                return event
        return None

    def _shrink_levels(self, item) -> list:
        parts = [p for p in item.rubric if float(p.get("points") or 0) > 0]
        if len(parts) < 2:
            return [(e, s, []) for e, s in DEFAULT_SHRINK]
        given = [float(p["minutes"]) for p in parts if p.get("minutes")]
        mean = sum(given) / len(given) if given else 1.0
        shares = [float(p.get("minutes") or mean) for p in parts]
        total_share, total_points = sum(shares), sum(float(p["points"]) for p in parts)
        ranked = sorted(range(len(parts)), key=lambda k: float(parts[k]["points"]) / shares[k])
        levels = []
        for k in sorted({math.ceil(len(parts) / 3), math.ceil(2 * len(parts) / 3)}):
            if k >= len(parts):
                continue
            light = set(ranked[:k])
            effort_share = sum(shares[j] * (LIGHT_EFFORT if j in light else 1) for j in range(len(parts)))
            score = sum(float(parts[j]["points"]) * (LIGHT_CREDIT if j in light else 1) for j in range(len(parts)))
            levels.append((effort_share / total_share, score / total_points,
                           [{"part": parts[j].get("part") or f"part {j + 1}", "points": parts[j]["points"],
                             "of": total_points} for j in sorted(light)]))
        return levels

    def _late_options(self, item, remaining: float) -> list:
        course = self.state.courses.get(item.course_id)
        policy = (course.model.get("late_policy") if course else None) or {}
        opts = []
        now, horizon = self.state.now, self.state.horizon_end
        accepts = policy.get("accepts_late", bool(policy.get("penalty_per_day")))
        max_days = int(policy.get("max_days") or (3 if accepts else 0))
        penalty = float(policy.get("penalty_per_day") or 0)
        for d in (range(1, max_days + 1) if accepts else []):
            deadline = item.due + timedelta(days=d)
            if deadline <= now or deadline > horizon:
                continue
            if item.available_until and deadline > item.available_until:
                break
            opts.append(Option("late", remaining, max(0.0, 1 - penalty * d / 100.0), deadline=deadline, late_days=d))
        budget = self._late_days_left(course)
        for d in range(1, (budget or 0) + 1):
            deadline = item.due + timedelta(days=d)
            if deadline <= now or deadline > horizon:
                continue
            if item.available_until and deadline > item.available_until:
                break
            opts.append(Option("late", remaining, 1.0, deadline=deadline, late_days=d, uses_late_days=True))
        return opts

    def _late_days_left(self, course) -> int:
        if course is None:
            return 0
        budget = int(((course.model.get("late_policy") or {}).get("late_days_budget")) or 0)
        if not budget:
            return 0
        if course.late_days_left is None:
            note = f"{course.name}: assumed all {budget} late days are still unused"
            if note not in self.assumptions:
                self.assumptions.append(note)
            return budget
        return max(0, course.late_days_left)

    def _baseline(self):
        """Grades if the student did everything in full; sets each course's multiplier and risk."""
        full_sel = {}
        for item in self.flexible():
            opts = self.options[item.id]
            best = max(range(len(opts)), key=lambda k: (opts[k].kind in ("full", "attend", "study"),
                                                        opts[k].score, opts[k].minutes))
            full_sel[item.id] = best
        self.full_sel = full_sel
        self.mult, self.fail_risk, self.base_pct = {}, {}, {}
        for cid, course in self.state.courses.items():
            pct = course_percent(course, self.course_items[cid], self._earned(course, full_sel))
            self.base_pct[cid] = pct
            _, cutoff = target_cutoff(course, pct)
            d = pct - cutoff
            if pct < course.pass_percent() + FAIL_MARGIN:
                m, risk = MAX_BOOST, True
            elif abs(d) <= NEAR_CUTOFF:
                m, risk = 1 + (MAX_BOOST - 1) * (1 - abs(d) / NEAR_CUTOFF), False
            elif d > SAFE_MARGIN:
                m, risk = SAFE_FACTOR, False
            else:
                m, risk = 1.0, False
            self.mult[cid], self.fail_risk[cid] = m, risk

    def _floors(self):
        """Starting choice per item: skip, or the cheapest acceptable option for must-do work."""
        self.must, self.floor = {}, {}
        gate_groups = {(cid, g["group"]) for cid, c in self.state.courses.items() for g in c.model.get("gates") or []}
        sel = {}
        for item in self.flexible():
            opts = self.options[item.id]
            reason = None
            if item.kind in ("prep", "study"):
                reason = "prep" if item.kind == "prep" else None
            elif item.must_do:
                reason = "must_do"
            elif item.group_project:
                reason = "group_project"
            elif item.kind == "graded" and (item.course_id, item.group) in gate_groups:
                reason = "gate"
            elif item.kind == "graded" and self.fail_risk.get(item.course_id):
                reason = "fail_risk"
            elif item.kind == "graded" and item.prepares_for:
                reason = "exam_prep"
            idx = 0
            if reason:
                self.must[item.id] = reason
                non_skip = [k for k, o in enumerate(opts) if o.kind not in ("skip", "late")]
                if reason == "group_project":
                    non_skip = [k for k, o in enumerate(opts) if o.kind == "full"]
                if not non_skip:
                    non_skip = [k for k, o in enumerate(opts) if o.kind != "skip"]
                if non_skip:
                    idx = min(non_skip, key=lambda k: opts[k].minutes)
            forced = self.forced.get(item.id)
            if forced == "skip":
                idx = 0
                self.must.pop(item.id, None)
            sel[item.id] = idx
            self.floor[item.id] = idx
        self.start_sel = sel

    # ------------------------------------------------------------ value

    def _expected(self, course, item) -> float:
        key = (course.id, item.group)
        if key not in self._avg:
            self._avg[key] = group_average(course, item.group)
        avg, source = self._avg[key]
        if source == "assumed":
            note = f"{course.name}: no grades yet, so future work is assumed at {round(avg * 100)}%"
            if note not in self.assumptions:
                self.assumptions.append(note)
        return avg

    def _study_hours(self, exam, sel) -> float:
        hours = self.options[f"study:{exam.id}"][sel[f"study:{exam.id}"]].minutes / 60.0
        for item_id in self.links.get(exam.id, []):
            opt = self.options[item_id][sel[item_id]]
            hours += exams_mod.PREP_CREDIT * opt.minutes / 60.0
        return hours

    def _earned(self, course, sel) -> dict:
        earned = {}
        avg = course_average(course)
        for item in self.course_items[course.id]:
            if item.kind == "exam":
                earned[item.id] = exams_mod.expected_score(avg, self._study_hours(item, sel)) * item.points
            elif item.kind == "attendance":
                earned[item.id] = item.points if self.options[item.id][sel[item.id]].kind == "attend" else 0.0
            elif item.kind == "graded":
                opt = self.options[item.id][sel[item.id]]
                earned[item.id] = opt.score * self._expected(course, item) * item.points
        return earned

    def percent(self, cid: str, sel) -> float:
        course = self.state.courses[cid]
        return course_percent(course, self.course_items[cid], self._earned(course, sel))

    def utility(self, cid: Optional[str], sel) -> float:
        if cid is None:
            return sum(TODO_VALUE_PER_HOUR * self.options[i.id][sel[i.id]].minutes / 60.0
                       for i in self.flexible() if i.kind == "todo")
        course = self.state.courses[cid]
        earned = self._earned(course, sel)
        u = self.mult[cid] * course_percent(course, self.course_items[cid], earned)
        if course.model.get("gates") and gates_failed(course, self.course_items[cid], earned):
            u -= GATE_PENALTY
        return u

    # ------------------------------------------------------------ feasibility

    def _tasks(self, sel) -> tuple:
        tasks, attended = [], []
        for item in self.flexible():
            opt = self.options[item.id][sel[item.id]]
            if opt.kind == "attend":
                attended.append(item.id)
            elif opt.minutes > 0:
                tasks.append({"id": item.id, "minutes": opt.minutes, "release": item.opens,
                              "deadline": opt.deadline or self.state.horizon_end})
        return tasks, attended

    def _late_days_ok(self, sel) -> bool:
        used = {}
        for item in self.flexible():
            opt = self.options[item.id][sel[item.id]]
            if opt.uses_late_days:
                used[item.course_id] = used.get(item.course_id, 0) + opt.late_days
        return all(days <= self._late_days_left(self.state.courses[cid]) for cid, days in used.items())

    def shortfall(self, sel) -> float:
        if not self._late_days_ok(sel):
            return float("inf")
        tasks, attended = self._tasks(sel)
        short, _, _ = self.cal.schedule(tasks, attended)
        return short

    # ------------------------------------------------------------ search

    def run(self) -> Plan:
        sel = dict(self.start_sel)
        short = self.shortfall(sel)
        if short > 0.5:
            sel, short = self._rescue(sel)
        blocked = set()
        while True:
            candidates = self._candidates(sel, blocked)
            if not candidates:
                break
            applied = False
            for _, item_id, k in candidates:
                trial = dict(sel)
                trial[item_id] = k
                if self.shortfall(trial) <= max(short, 0.5):
                    sel = trial
                    applied = True
                    break
                blocked.add((item_id, k))
            if not applied:
                break
        return self._plan(sel)

    def _rescue(self, sel) -> tuple:
        """Must-do work doesn't fit: move what the syllabus lets you hand in late, earliest deadline first."""
        best = self.shortfall(sel)
        movable = sorted((i for i in self.flexible() if i.id in self.must and self.must[i.id] != "group_project"),
                         key=lambda i: i.due or self.state.horizon_end)
        for item in movable:
            for k, opt in enumerate(self.options[item.id]):
                if opt.kind != "late":
                    continue
                trial = dict(sel)
                trial[item.id] = k
                short = self.shortfall(trial)
                if short < best:
                    sel, best = trial, short
                    break
            if best <= 0.5:
                break
        return sel, best

    def _candidates(self, sel, blocked) -> list:
        base = {}
        out = []
        for item in self.flexible():
            if self.forced.get(item.id) == "skip" or item.kind == "prep":
                continue
            opts = self.options[item.id]
            cur = opts[sel[item.id]]
            if item.kind == "study":
                choices = list(range(sel[item.id] + 1, len(opts)))  # look past flat stretches (replacement rules)
            else:
                choices = [k for k, o in enumerate(opts)
                           if k != sel[item.id] and o.minutes >= cur.minutes and o.kind != "skip"]
            cid = item.course_id if item.kind != "todo" else None
            if cid not in base:
                base[cid] = self.utility(cid, sel)
            for k in choices:
                if (item.id, k) in blocked:
                    continue
                trial = dict(sel)
                trial[item.id] = k
                gain = self.utility(cid, trial) - base[cid]
                if gain <= 1e-9:
                    continue
                extra = opts[k].minutes - cur.minutes
                density = gain / max(extra, 1.0) * 60
                if self.full_minutes[item.id] <= QUICK_WIN_MINUTES:
                    density += 1000  # quick wins go first
                out.append((-density, item.id, k))
        out.sort()
        return out

    # ------------------------------------------------------------ result

    def _plan(self, sel) -> Plan:
        tasks, attended = self._tasks(sel)
        short, blocks, late = self.cal.schedule(tasks, attended, quick_first=True)
        plain_short, plain_blocks, plain_late = self.cal.schedule(tasks, attended)
        if short > plain_short + 0.5:
            short, blocks, late = plain_short, plain_blocks, plain_late
        for item_id in attended:
            item = self.by_id[item_id]
            blocks.append({"id": item_id, "start": item.start, "end": item.end, "minutes": self.full_minutes[item_id],
                           "fixed": True})
        for exam in self.exams:
            blocks.append({"id": exam.id, "start": exam.start, "end": exam.end, "minutes": 0, "fixed": True})
        for event in self.state.events:
            blocks.append({"id": f"event:{event.id}", "title": event.title, "start": event.start, "end": event.end,
                           "minutes": 0, "fixed": True})
        blocks.sort(key=lambda b: b["start"])

        decisions = [self._decision(item, sel) for item in self.flexible()]
        projections = {}
        for cid, course in self.state.courses.items():
            plan_pct = self.percent(cid, sel)
            letter, cutoff = target_cutoff(course, self.base_pct[cid])
            projections[cid] = {
                "name": course.name, "if_everything": round(self.base_pct[cid], 2), "with_plan": round(plan_pct, 2),
                "letter_if_everything": letter_for(course, self.base_pct[cid]),
                "letter_with_plan": letter_for(course, plan_pct), "protecting": letter, "cutoff": cutoff,
                "multiplier": round(self.mult[cid], 2), "fail_risk": self.fail_risk[cid],
            }
        return Plan(
            state=self.state, calendar=self.cal, decisions=decisions, blocks=blocks, shortfall=short,
            projections=projections, headline=self._headline(), assumptions=self._all_assumptions(),
            warnings=collisions(self.state) + ([f"Couldn't fit all of: {', '.join(self.by_id[i].title for i in late)}"]
                                               if late else []),
            insights=effort_mod.insights(self.learned, {c: v.name for c, v in self.state.courses.items()}),
            priors=dict(self.prior_minutes),
        )

    def _decision(self, item, sel) -> Decision:
        opts = self.options[item.id]
        opt = opts[sel[item.id]]
        cid = item.course_id if item.kind not in ("todo", "prep") else None
        notes = {}
        full_idx = next((k for k, o in enumerate(opts) if o.kind in ("full", "attend")), len(opts) - 1)
        if cid:
            skip_sel = dict(sel)
            skip_sel[item.id] = 0
            full_sel = dict(sel)
            full_sel[item.id] = full_idx
            skip_pct = self.percent(cid, skip_sel)
            value = self.percent(cid, sel) - skip_pct
            full_value = self.percent(cid, full_sel) - skip_pct
            if item.kind == "attendance" and len(opts) == 1:  # can't attend: show what the clash costs
                course = self.state.courses[cid]
                share = item.points / max(1.0, float(course.groups[item.group].get("count") or 1) * item.points)
                full_value = float(course.groups[item.group].get("weight") or 0) * share
        else:
            value = full_value = 0.0
        if item.kind == "study":
            verdict = "DO" if opt.minutes > 0 else "SKIP"
            exam = self.by_id[item.id.split(":", 1)[1]]
            notes["exam"] = exam.title
            notes["exam_at"] = exam.start
            course = self.state.courses[cid]
            notes["expected_score"] = round(100 * exams_mod.expected_score(course_average(course),
                                                                           self._study_hours(exam, sel)))
        elif opt.kind in ("full", "attend"):
            verdict = "DO"
        elif opt.kind == "shrink":
            verdict = "SHRINK"
            notes["light_parts"] = opt.light_parts
            notes["score_share"] = opt.score
        elif opt.kind == "late":
            verdict = "SHIFT"
            notes["late_days"] = opt.late_days
            notes["uses_late_days"] = opt.uses_late_days
            notes["late_score_share"] = opt.score
        else:
            verdict = "SKIP"
        reason = self.must.get(item.id)
        if reason:
            notes["must"] = reason
        if item.kind == "prep":
            notes["protects"] = item.title.replace("Prep: ", "", 1)
        if item.kind == "attendance" and self._conflict(item):
            notes["conflict"] = self._conflict(item).title
        if self.full_minutes[item.id] <= QUICK_WIN_MINUTES and item.kind in ("graded", "todo"):
            notes["quick_win"] = True
        if item.kind == "graded":
            group = self.state.courses[cid].groups.get(item.group, {})
            if group.get("drop_lowest"):
                notes["drop_lowest"] = int(group["drop_lowest"])
                notes["group_name"] = group.get("name") or item.group
            policy = self.state.courses[cid].model.get("late_policy") or {}
            if verdict in ("SKIP", "SHRINK") and full_value >= 1.0 and policy.get("extensions") == "on request":
                notes["extension"] = True
            if policy.get("quote"):
                notes["late_quote"] = policy["quote"]
        if item.prepares_for and item.kind != "study":
            names = [self.by_id[e].title for e in item.prepares_for if e in self.by_id]
            if names:
                notes["prepares_for"] = names
        if self.forced.get(item.id):
            notes["forced"] = self.forced[item.id]
        return Decision(item=item, option=opt, verdict=verdict, value=value, full_value=full_value,
                        full_minutes=self.full_minutes[item.id] * (1 - item.progress),
                        multiplier=self.mult.get(cid, 1.0) if cid else 1.0, notes=notes)

    def _headline(self) -> dict:
        now = self.state.now
        deadlines = [i.due for i in self.items if i.due and i.kind not in ("attendance",)]
        last = max(deadlines) if deadlines else self.state.horizon_end
        last = min(last, self.state.horizon_end)
        work = sorted(((self.options[i.id][self.full_sel[i.id]].deadline or self.state.horizon_end,
                        self.full_minutes[i.id] * (1 - i.progress)) for i in self.flexible()), key=lambda x: x[0])
        demand = sum(m for _, m in work)
        free = self.cal.capacity(last)  # class time that earns attendance points counts as free here
        # The crunch is the tightest window: work due by some deadline vs time available before it.
        worst = {"over": demand - free, "until": last, "work": demand, "free": free}
        running = 0.0
        for deadline, minutes in work:
            running += minutes
            available = self.cal.capacity(deadline)
            if running - available > worst["over"]:
                worst = {"over": running - available, "until": deadline, "work": running, "free": available}
        if worst["over"] <= 0:
            worst = {"over": demand - free, "until": last, "work": demand, "free": free}
        deliverables = sum(1 for i in self.items if i.kind in ("graded", "exam") and
                           (i.due or self.state.horizon_end) <= worst["until"])
        days = max(1, math.ceil((worst["until"] - now).total_seconds() / 86400))
        return {"days": days, "deliverables": deliverables, "work_hours": worst["work"] / 60,
                "free_hours": worst["free"] / 60, "over_hours": max(0.0, worst["over"] / 60),
                "until": worst["until"], "total_work_hours": demand / 60, "total_free_hours": free / 60}

    def _all_assumptions(self) -> list:
        out = list(self.assumptions)
        for cid, course in self.state.courses.items():
            for rule in course.model.get("replacement") or []:
                if any(g["group"] == rule.get("from") for g in course.graded):
                    continue
                src = course.groups.get(rule.get("from"), {}).get("name") or rule.get("from")
                dst = course.groups.get(rule.get("to"), {}).get("name") or rule.get("to")
                out.append(f"{course.name}: not counting on '{src} replaces lowest {dst}' until {src} is graded")
            unknown = [g.get("name") or gid for gid, g in course.groups.items()
                       if g.get("count") is None and any(i.group == gid for i in self.course_items[cid])]
            if unknown:
                out.append(f"{course.name}: no item count for {', '.join(unknown)}, so values use only the items "
                           "known so far")
        priors = [i.title for i in self.flexible()
                  if i.kind in ("graded", "todo") and effort_mod.prior_minutes(i)[1] == "prior"]
        if priors:
            out.append(f"Time estimates are typical values for {len(priors)} item(s) "
                       "(tell me how long they really take and I'll learn)")
        return out


def make_plan(state, effort_log: dict, forced: Optional[dict] = None) -> Plan:
    return Planner(state, effort_log, forced).run()
