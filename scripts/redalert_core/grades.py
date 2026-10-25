"""Course grades the way the syllabus computes them.

Handles weighted-by-group and total-points courses, drop-lowest rules, "final replaces lowest midterm" rules,
extra credit and gates. Items not graded yet are filled in at the student's average so far (an assumption the
plan states), so the value of any single item can be found by computing the grade with and without it.
"""

from __future__ import annotations

DEFAULT_AVERAGE = 0.85


def group_average(course, group_id: str) -> tuple:
    """(fraction, source) the student tends to score in a group on work they hand in, for items not graded yet.

    Zeros are left out: they are usually missed work, and the plan decides separately whether to skip an item.
    """
    rows = [g for g in course.graded if g["group"] == group_id and g["out_of"] > 0 and g["score"] > 0]
    if rows:
        return sum(g["score"] for g in rows) / sum(g["out_of"] for g in rows), "group"
    rows = [g for g in course.graded if g["out_of"] > 0 and g["score"] > 0]
    if rows:
        return sum(g["score"] for g in rows) / sum(g["out_of"] for g in rows), "course"
    if course.current_percent is not None:
        return course.current_percent / 100.0, "canvas"
    return DEFAULT_AVERAGE, "assumed"


def course_average(course) -> float:
    rows = [g for g in course.graded if g["out_of"] > 0]
    if rows:
        return sum(g["score"] for g in rows) / sum(g["out_of"] for g in rows)
    if course.current_percent is not None:
        return course.current_percent / 100.0
    return DEFAULT_AVERAGE


def _entries(course, items, earned: dict) -> tuple:
    """Per group: [earned, possible, kind] rows (kind: graded, planned, placeholder), plus extra credit points."""
    groups = course.groups
    rows = {gid: [] for gid in groups}
    extra = {gid: 0.0 for gid in groups}
    for g in course.graded:
        if g["group"] in rows:
            if g["out_of"] > 0:
                rows[g["group"]].append([g["score"], g["out_of"], "graded"])
            else:
                extra[g["group"]] += g["score"]
    for item in items:
        if item.course_id != course.id or item.group not in rows:
            continue
        if item.extra_credit or item.points <= 0:
            extra[item.group] += earned.get(item.id, 0.0)
        else:
            rows[item.group].append([earned.get(item.id, 0.0), item.points, "planned"])
    for gid, group in groups.items():
        count = group.get("count")
        if count is None:
            continue
        missing = int(count) - len(rows[gid])
        if missing <= 0:
            continue
        known = rows[gid]
        possible = (sum(r[1] for r in known) / len(known)) if known else float(group.get("points_each") or 100)
        avg, _ = group_average(course, gid)
        rows[gid].extend([possible * avg, possible, "placeholder"] for _ in range(missing))
    return rows, extra


def _percent(rows: list) -> float:
    possible = sum(r[1] for r in rows)
    return sum(r[0] for r in rows) / possible if possible > 0 else 0.0


def group_percents(course, items, earned: dict) -> dict:
    """({group_id: fraction or None}, rows, extra) after drops and replacements."""
    rows, extra = _entries(course, items, earned)
    for gid, group in course.groups.items():
        drop = int(group.get("drop_lowest") or 0)
        if drop and len(rows[gid]) > 1:
            drop = min(drop, len(rows[gid]) - 1)
            rows[gid].sort(key=lambda r: r[0] / r[1] if r[1] else 0)
            rows[gid] = rows[gid][drop:]
    for rule in course.model.get("replacement") or []:
        src, dst = rule.get("from"), rule.get("to")
        if not rows.get(src) or not rows.get(dst):
            continue
        if any(r[2] != "graded" for r in rows[src]):
            continue  # safe side: never count on a future exam to replace a score
        src_pct = _percent(rows[src])
        lowest = min(rows[dst], key=lambda r: r[0] / r[1] if r[1] else 0)
        if lowest[1] and src_pct > lowest[0] / lowest[1]:
            lowest[0] = src_pct * lowest[1]
    out = {}
    for gid in course.groups:
        possible = sum(r[1] for r in rows[gid])
        if possible > 0:
            out[gid] = (sum(r[0] for r in rows[gid]) + extra[gid]) / possible
        else:
            out[gid] = None
    return out, rows, extra


def course_percent(course, items, earned: dict) -> float:
    """The projected course grade in percent."""
    pcts, rows, extra = group_percents(course, items, earned)
    groups = course.groups
    if course.model.get("scheme", "weighted") == "points":
        possible = sum(r[1] for gid in groups for r in rows[gid])
        got = sum(r[0] for gid in groups for r in rows[gid]) + sum(extra.values())
        return 100.0 * got / possible if possible > 0 else 0.0
    total = weight = 0.0
    for gid, group in groups.items():
        pct = pcts[gid]
        w = float(group.get("weight") or 0)
        if pct is None:
            continue
        if group.get("extra_credit"):
            total += w * pct  # on top of 100%
        else:
            total += w * pct
            weight += w
    return 100.0 * total / weight if weight > 0 else 0.0


def gates_failed(course, items, earned: dict) -> list:
    pcts, _, _ = group_percents(course, items, earned)
    failed = []
    for gate in course.model.get("gates") or []:
        pct = pcts.get(gate["group"])
        if pct is not None and pct * 100 < float(gate.get("min_percent") or 0):
            failed.append(gate)
    return failed


def letter_for(course, percent: float) -> str:
    for letter, cutoff in course.cutoffs():
        if percent >= cutoff:
            return letter
    return "F"


REACH = 1.0  # with no target set, a letter this close above counts as the one to aim for


def target_cutoff(course, percent: float) -> tuple:
    """(letter, cutoff) the plan protects: the student's target, else the letter they hold (or nearly hold)."""
    cuts = course.cutoffs()
    if course.target and course.target in dict(cuts):
        return course.target, dict(cuts)[course.target]
    above = [(k, v) for k, v in cuts if v > percent]
    if above and above[-1][1] - percent <= REACH:
        return above[-1]
    letter = letter_for(course, percent)
    return letter, dict(cuts).get(letter, course.pass_percent())


def unknown_count_groups(course) -> list:
    return [g["name"] if g.get("name") else gid for gid, g in course.groups.items() if g.get("count") is None]
