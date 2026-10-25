"""One short reason per decision, with the numbers behind it. Cubbie may reword these but keeps the numbers."""

from __future__ import annotations

from datetime import timedelta


def minutes(m: float) -> str:
    m = max(0.0, float(m))
    if m < 60:
        return f"{int(round(m / 5.0) * 5) or 5} min"
    h = round(m / 30.0) / 2
    return f"{h:g} h"


def points(v: float) -> str:
    v = abs(v)
    if v < 0.1:
        return f"{v:.2f} pt"
    return f"{v:.1f} pt"


def per_hour(value: float, mins: float) -> str:
    if mins <= 0:
        return ""
    rate = value / (mins / 60.0)
    return f"{rate:.2f} pt/h" if rate < 0.1 else f"{rate:.1f} pt/h"


def when(dt, now) -> str:
    delta = dt - now
    if delta < timedelta(hours=1):
        return f"in {max(1, int(delta.total_seconds() // 60))} min"
    if delta < timedelta(hours=36):
        return f"in {int(delta.total_seconds() // 3600)} h"
    return dt.strftime("%a %b ") + str(dt.day)


def clock(dt) -> str:
    text = dt.strftime("%I:%M %p").lstrip("0")
    return text.replace(":00 ", " ")


def _course(plan, item) -> str:
    course = plan.state.courses.get(item.course_id)
    return f" ({course.name})" if course and not item.title.startswith(course.name) else ""


def _boost(plan, d) -> str:
    proj = plan.projections.get(d.item.course_id)
    if not proj or proj["multiplier"] < 1.2:
        return ""
    if proj["fail_risk"]:
        return f" {proj['name']} is close to failing, so its points count {proj['multiplier']:g}x."
    gap = proj["if_everything"] - proj["cutoff"]
    if abs(gap) < 0.05:
        where = f"right at the {proj['protecting']} line"
    else:
        where = f"{abs(gap):.1f} {'above' if gap > 0 else 'below'} the {proj['protecting']} line"
    return f" {proj['name']} is {where}, so its points count {proj['multiplier']:g}x."


def _must(d) -> str:
    return {
        "gate": " You have to pass this part to pass the course.",
        "fail_risk": "",
        "group_project": " Group project: your share stays in.",
        "exam_prep": "",
        "must_do": " You marked it as a must.",
    }.get(d.notes.get("must"), "")


def reason(plan, d) -> str:
    item, now = d.item, plan.state.now
    name = f"{item.title}{_course(plan, item)}"
    due = f", due {when(item.due, now)}" if item.due else ""
    covers = f" It covers {', '.join(d.notes['prepares_for'])}." if d.notes.get("prepares_for") else ""
    if item.kind == "study":
        if d.verdict == "SKIP":
            return f"No extra study time fits for {d.notes['exam']} beyond the work that covers it."
        return (f"Study {minutes(d.minutes)} for {d.notes['exam']} ({when(d.notes['exam_at'], now)}): "
                f"worth {points(d.value)}, expected score about {d.notes['expected_score']}%.{_boost(plan, d)}")
    if item.kind == "prep":
        return f"Prep for {d.notes['protects']}: {minutes(d.minutes)}, protected. It's never traded for points."
    if item.kind == "todo":
        if d.verdict == "SKIP":
            return f"{item.title}: no grade riding on it and no room this time. Push it past the crunch."
        return f"{item.title}: {minutes(d.minutes)}, fits without costing grade work."
    if item.kind == "attendance":
        if d.notes.get("conflict"):
            return f"Skip {name}: it clashes with {d.notes['conflict']}, which comes first ({points(d.full_value)} lost)."
        if d.verdict == "SKIP":
            return (f"Skip {name}: {points(d.full_value)} for {minutes(d.full_minutes)}, and that hour is worth more "
                    "elsewhere this week.")
        return f"Go to {name}: {points(d.value)} for showing up.{covers}"
    if d.verdict == "DO":
        quick = " Quick win." if d.notes.get("quick_win") else ""
        if not quick and d.minutes >= 60 and d.value / (d.minutes / 60.0) < 0.1:
            quick = " Low value, but it fits."
        return (f"{name}: {minutes(d.minutes)} for {points(d.value)} ({per_hour(d.value, d.minutes)}){due}."
                f"{quick}{_must(d)}{covers}{_boost(plan, d)}")
    if d.verdict == "SHRINK":
        saved = d.full_minutes - d.minutes
        light = d.notes.get("light_parts") or []
        how = ""
        if light:
            parts = ", ".join(f"{p['part']} ({p['points']:g}/{p['of']:g})" for p in light)
            how = f" Go light on {parts}."
        return (f"{name}: aim for good enough, about {round(d.notes['score_share'] * 100)}% of full credit, in "
                f"{minutes(d.minutes)} instead of {minutes(d.full_minutes)}: saves {minutes(saved)} for "
                f"{points(d.full_value - d.value)}.{how}{covers}{_must(d)}")
    if d.verdict == "SHIFT":
        days = d.notes["late_days"]
        if d.notes.get("uses_late_days"):
            return (f"{name}: use {days} late day{'s' if days > 1 else ''} (no penalty) and do it after the "
                    "tighter deadlines.")
        penalty = round((1 - d.notes["late_score_share"]) * 100)
        return (f"{name}: hand it in {days} day{'s' if days > 1 else ''} late for -{penalty}% (still "
                f"{points(d.value)}) instead of rushing it{due}.")
    drop = ""
    if d.notes.get("drop_lowest") and d.full_value < 0.5:
        n = d.notes["drop_lowest"]
        group = d.notes["group_name"]
        drop = (f", and the lowest {group} score is dropped" if n == 1
                else f", and the lowest {n} {group} scores are dropped")
    ext = " If you'd rather do it, I can draft an extension request." if d.notes.get("extension") else ""
    return (f"Skip {name}: {minutes(d.full_minutes)} for {points(d.full_value)} "
            f"({per_hour(d.full_value, d.full_minutes)}){drop}.{ext}")
