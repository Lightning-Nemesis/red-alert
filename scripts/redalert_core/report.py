"""Turn a plan into what Cubbie needs: a short text summary, the full plan as Markdown, or JSON."""

from __future__ import annotations

from collections import defaultdict

from .explain import clock, minutes, reason

MAX_TEXT = 7500  # Cubbie reads the first 8,000 characters of output
ORDER = {"DO": 0, "SHRINK": 1, "SHIFT": 2, "SKIP": 3}


def headline(plan) -> str:
    h = plan.headline
    base = (f"{h['days']} days, {h['deliverables']} deliverables, ~{h['work_hours']:.0f} h of work, "
            f"{h['free_hours']:.0f} free hours.")
    if h["over_hours"] >= 1:
        return f"RED ALERT: {base} You're {h['over_hours']:.0f} h over."
    if h["work_hours"] > 0.85 * h["free_hours"]:
        return f"Tight: {base} It fits, barely."
    return f"No red alert: {base} You have room."


def is_alert(plan) -> bool:
    h = plan.headline
    return h["over_hours"] >= 1 or h["work_hours"] > 0.85 * h["free_hours"]


def _title(plan, block) -> str:
    if block.get("title"):
        return block["title"]
    item = next((d.item for d in plan.decisions if d.item.id == block["id"]), None)
    if item is None:
        item = next((i for i in plan.state.items if i.id == block["id"]), None)
    return item.title if item else block["id"]


def tonight(plan, limit=3) -> tuple:
    """(label, [(block, decision)]) for the next work blocks: tonight if any, else the next ones."""
    by_id = {d.item.id: d for d in plan.decisions}
    end = plan.calendar.tonight_end()
    work = [b for b in plan.blocks if not b.get("fixed") or b["id"] in by_id]
    work = [b for b in work if b["id"] in by_id and b["end"] > plan.state.now]
    first, seen = [], set()
    for b in work:
        if b["id"] in seen:
            continue
        seen.add(b["id"])
        first.append((b, by_id[b["id"]]))
    tonight_blocks = [x for x in first if x[0]["start"] < end]
    if tonight_blocks:
        return f"Tonight (until {clock(end)})", tonight_blocks[:limit]
    return "Next up", first[:limit]


def _sorted(plan) -> list:
    return sorted(plan.decisions, key=lambda d: (ORDER[d.verdict], -(d.value if d.verdict != "SKIP" else d.full_value)))


def counts(plan) -> dict:
    out = defaultdict(int)
    for d in plan.decisions:
        if d.item.kind in ("graded", "attendance", "study", "todo", "prep"):
            out[d.verdict] += 1
    return dict(out)


def text(plan, plan_path=None) -> str:
    lines = [headline(plan), ""]
    label, nxt = tonight(plan)
    lines.append(f"{label}:")
    for n, (block, d) in enumerate(nxt, 1):
        start = block["start"]
        day = "" if start.date() == plan.state.now.date() else start.strftime("%a ")
        lines.append(f"{n}. {day}{clock(max(start, plan.state.now))}: {reason(plan, d)}")
    if not nxt:
        lines.append("Nothing scheduled.")
    c = counts(plan)
    lines += ["", "Decisions: " + ", ".join(f"{k} {c[k]}" for k in ORDER if c.get(k))]
    for verdict in ("SKIP", "SHRINK", "SHIFT"):
        picked = [d for d in _sorted(plan) if d.verdict == verdict and d.item.kind != "study"]
        if picked:
            lines.append(f"{verdict.title()}:")
            lines += [f"- {reason(plan, d)}" for d in picked[:5]]
            if len(picked) > 5:
                lines.append(f"- and {len(picked) - 5} more in the full plan")
    if plan.shortfall > 0.5:
        lines.append(f"Even the essentials need {minutes(plan.shortfall)} more than you have. Talk to me about "
                     "extensions or what to drop.")
    warnings = [w for w in plan.warnings if w]
    if warnings:
        lines += ["", "Heads-up:"] + [f"- {w}" for w in warnings[:4]]
    lines += ["", "Grades:"]
    for p in plan.projections.values():
        lines.append(f"- {p['name']}: {p['letter_with_plan']} with this plan ({p['with_plan']:.1f}%; "
                     f"{p['if_everything']:.1f}% if you did everything)")
    if plan.insights:
        lines += [""] + plan.insights
    if plan.assumptions:
        lines += ["", "Assumptions:"] + [f"- {a}" for a in plan.assumptions[:5]]
    if plan_path:
        lines += ["", f"Full plan: {plan_path}"]
    out = "\n".join(lines)
    return out if len(out) <= MAX_TEXT else out[:MAX_TEXT - 40] + "\n... (see the full plan)"


def markdown(plan) -> str:
    now = plan.state.now
    lines = ["# Red Alert plan", "", f"Made {now.strftime('%a %b')} {now.day}, {clock(now)}.", "", headline(plan), ""]
    lines += ["## Decisions", ""]
    for verdict in ("DO", "SHRINK", "SHIFT", "SKIP"):
        picked = [d for d in _sorted(plan) if d.verdict == verdict]
        if not picked:
            continue
        lines.append(f"### {verdict}")
        lines.append("")
        lines += [f"- {reason(plan, d)}" for d in picked]
        lines.append("")
    lines += ["## Schedule", ""]
    by_day = defaultdict(list)
    for b in plan.blocks:
        if b["end"] > now:
            by_day[b["start"].date()].append(b)
    for day in sorted(by_day):
        lines.append(f"### {day.strftime('%a %b')} {day.day}")
        lines.append("")
        for b in by_day[day]:
            tag = " (fixed)" if b.get("fixed") else ""
            lines.append(f"- {clock(b['start'])}-{clock(b['end'])}: {_title(plan, b)}{tag}")
        lines.append("")
    lines += ["## Grades", "", "| Course | With this plan | If you did everything | Protecting |", "| --- | --- | --- | --- |"]
    for p in plan.projections.values():
        lines.append(f"| {p['name']} | {p['letter_with_plan']} ({p['with_plan']:.1f}%) | {p['letter_if_everything']} "
                     f"({p['if_everything']:.1f}%) | {p['protecting']} at {p['cutoff']:g}% |")
    lines.append("")
    warnings = [w for w in plan.warnings if w]
    if warnings:
        lines += ["## Heads-up", ""] + [f"- {w}" for w in warnings] + [""]
    if plan.assumptions:
        lines += ["## Assumptions", ""] + [f"- {a}" for a in plan.assumptions] + [""]
    lines.append("pt = percentage points of the course grade. Nothing here is submitted or sent for you.")
    return "\n".join(lines) + "\n"


def as_json(plan) -> dict:
    def iso(dt):
        return dt.isoformat() if dt else None

    label, nxt = tonight(plan)
    return {
        "headline": headline(plan),
        "alert": is_alert(plan),
        "numbers": {k: (iso(v) if k == "until" else round(v, 1) if isinstance(v, float) else v)
                    for k, v in plan.headline.items()},
        "next_label": label,
        "next": [{"id": d.item.id, "start": iso(b["start"]), "reason": reason(plan, d)} for b, d in nxt],
        "decisions": [
            {"id": d.item.id, "title": d.item.title, "course_id": d.item.course_id, "kind": d.item.kind,
             "verdict": d.verdict, "minutes": round(d.minutes), "full_minutes": round(d.full_minutes),
             "points": round(d.value, 3), "full_points": round(d.full_value, 3), "due": iso(d.item.due),
             "url": d.item.url, "reason": reason(plan, d), "must": d.notes.get("must"),
             "group_project": d.item.group_project, "extension_draft": bool(d.notes.get("extension"))}
            for d in _sorted(plan)
        ],
        "blocks": [{"id": b["id"], "title": _title(plan, b), "start": iso(b["start"]), "end": iso(b["end"]),
                    "fixed": bool(b.get("fixed"))} for b in plan.blocks if b["end"] > plan.state.now],
        "grades": plan.projections,
        "shortfall_minutes": round(plan.shortfall),
        "warnings": [w for w in plan.warnings if w],
        "assumptions": plan.assumptions,
        "insights": plan.insights,
    }


def saved(plan, previous=None) -> dict:
    """What plan.json keeps between conversations: the items, their verdicts and the crunch window."""
    now = plan.state.now.isoformat()
    items = {}
    for d in plan.decisions:
        items[d.item.id] = {
            "title": d.item.title, "course_id": d.item.course_id, "type": d.item.type, "kind": d.item.kind,
            "verdict": d.verdict, "minutes": round(d.minutes), "full_minutes": round(d.full_minutes),
            "points": round(d.value, 3), "full_points": round(d.full_value, 3),
            "prior_minutes": round(plan.priors.get(d.item.id, d.full_minutes)),
            "due": d.item.due.isoformat() if d.item.due else None,
        }
    started = (previous or {}).get("started") or now
    return {"started": started, "updated": now, "until": plan.headline["until"].isoformat(), "items": items,
            "headline": headline(plan)}
