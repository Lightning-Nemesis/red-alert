#!/usr/bin/env python3
"""Red Alert: decide what to do, shrink, shift or skip when everything is due at once.

Cubbie gathers Canvas, the syllabus, Calendar, Gmail, Tasks and memory, writes them to a JSON file and runs a
command here. Nothing in this script calls any service. Saved state lives in ~/.config/red-alert/.

Commands:
  course --input course.json [--save]   check a course model built from the syllabus (save after the student confirms)
  scan   --input state.json             workload vs free time for the next weeks: is this a red alert?
  plan   --input state.json [--out F]   decisions with reasons, tonight's work and the full plan as Markdown
  whatif --input state.json --skip ID | --score ID=PCT   what changes if you skip something or score differently
  log    --item ID --minutes N [--done] record how long something really took
  recap                                 end-of-crunch summary
Add --sample to any command to use the bundled example (nothing is read from or written to saved state) and
--json for machine-readable output.

Exit codes: 0 ok, 2 bad arguments or input file, 3 a course has no saved course model, 4 a course model is
invalid, 5 nothing due in the plan window, 6 saved state unreadable.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from redalert_core import effort, report, store
from redalert_core.decide import make_plan
from redalert_core.model import CourseModelError, InputError, MissingCourse, load_state, read_json, validate_course

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SAMPLE_STATE = ASSETS / "sample_state.json"


def fail(message: str, code: int):
    print(message, file=sys.stderr)
    sys.exit(code)


def sample_models() -> dict:
    models = {}
    for path in sorted(ASSETS.glob("sample_course_*.json")):
        model = read_json(path)
        models[model["course_id"]] = model
    return models


def saved_models(raw_state: dict) -> dict:
    models = {}
    for entry in raw_state.get("courses") or []:
        cid = entry.get("course_id")
        model = store.load_course(cid) if cid else None
        if model is not None:
            models[cid] = model
    return models


def build_state(args):
    """(state, effort log, previous plan) for scan / plan / whatif."""
    if args.sample:
        raw = read_json(SAMPLE_STATE)
        return load_state(raw, sample_models()), {"entries": []}, None
    if not args.input:
        fail("--input is required (the state file Cubbie wrote; see references/state-format.md)", 2)
    raw = read_json(args.input)
    log = store.load_effort()
    previous = store.load_plan()
    state = load_state(raw, saved_models(raw))
    if previous and previous.get("until") and datetime.fromisoformat(previous["until"]) > state.now:
        apply_progress(state, log, previous)
    else:
        previous = None
    return state, log, previous


def apply_progress(state, log: dict, previous: dict) -> None:
    """Same crunch as last time: drop what was logged done, count logged minutes as progress."""
    done = set(effort.finished(log))
    kept = []
    for item in state.items:
        if item.id in done:
            continue
        spent = effort.logged_minutes(log, item.id)
        planned = (previous.get("items") or {}).get(item.id, {}).get("prior_minutes")
        if spent and planned:
            item.progress = min(0.9, max(item.progress, spent / float(planned)))
        kept.append(item)
    state.items = kept


def nothing_due(state) -> bool:
    return not any(i.kind in ("graded", "exam", "todo", "prep") for i in state.items)


def emit(args, payload: dict, text: str) -> None:
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(text)


# ---------------------------------------------------------------- commands


def cmd_course(args):
    path = ASSETS / "sample_course_econ.json" if args.sample else args.input
    if not path:
        fail("--input is required (the course model Cubbie built from the syllabus)", 2)
    model = read_json(path)
    errors, warnings = validate_course(model)
    if errors:
        fail("Course model problems:\n" + "\n".join(f"- {e}" for e in errors), 4)
    summary = course_summary(model)
    saved = None
    if args.save and not args.sample:
        saved = str(store.save_course(model))
    lines = [summary, "", "Rules found:"] + [f"- {line}" for line in rule_lines(model)]
    if warnings:
        lines += ["", "Check with the student:"] + [f"- {w}" for w in warnings]
    lines += ["", f"Saved: {saved}" if saved else "Not saved yet: run again with --save after the student confirms."]
    emit(args, {"course_id": model["course_id"], "summary": summary, "rules": rule_lines(model),
                "warnings": warnings, "saved": saved}, "\n".join(lines))


def course_summary(model: dict) -> str:
    parts = []
    for g in model["groups"]:
        bit = f"{g.get('name') or g['id']} {g.get('weight', 0):g}%" if model.get("scheme", "weighted") == "weighted" \
            else (g.get("name") or g["id"])
        if g.get("drop_lowest"):
            bit += f" (lowest {g['drop_lowest']} dropped)"
        parts.append(bit)
    late = model.get("late_policy") or {}
    if late.get("penalty_per_day"):
        parts.append(f"-{late['penalty_per_day']:g}% per day late, max {late.get('max_days', 3)} days")
    elif late.get("late_days_budget"):
        parts.append(f"{late['late_days_budget']} late days")
    elif late.get("accepts_late") is False:
        parts.append("no late work")
    for rule in model.get("replacement") or []:
        parts.append(f"{_group_name(model, rule['from'])} replaces the lowest {_group_name(model, rule['to'])}")
    for gate in model.get("gates") or []:
        parts.append(f"must pass {_group_name(model, gate['group'])} ({gate.get('min_percent', 60):g}%)")
    return f"{model.get('name') or model['course_id']}: " + ", ".join(parts) + ". Right?"


def rule_lines(model: dict) -> list:
    out = []
    for g in model["groups"]:
        count = f", {g['count']} item{'s' if int(g['count']) != 1 else ''}" if g.get("count") is not None else ""
        drop = f", lowest {g['drop_lowest']} dropped" if g.get("drop_lowest") else ""
        weight = f" {g.get('weight', 0):g}%" if model.get("scheme", "weighted") == "weighted" else ""
        out.append(f"{g.get('name') or g['id']}{weight}{count}{drop}" + _quote(g))
    if model.get("cutoffs"):
        cuts = ", ".join(f"{k} {v:g}" for k, v in sorted(model["cutoffs"].items(), key=lambda kv: -kv[1]))
        out.append(f"Cutoffs: {cuts}" + _quote(model, "cutoffs_quote"))
    late = model.get("late_policy")
    if late:
        bits = []
        if late.get("penalty_per_day"):
            bits.append(f"-{late['penalty_per_day']:g}% per day, max {late.get('max_days', 3)} days")
        if late.get("late_days_budget"):
            bits.append(f"{late['late_days_budget']} late days per term")
        if late.get("accepts_late") is False:
            bits.append("no late work")
        if late.get("extensions"):
            bits.append(f"extensions: {late['extensions']}")
        out.append("Late: " + ("; ".join(bits) or "see quote") + _quote(late))
    for p in model.get("participation") or []:
        days = "/".join(p.get("days") or [])
        out.append(f"Participation: {p.get('title') or p.get('id')}, {p.get('points_each', 1):g} pts each"
                   + (f", {days} {p.get('start')}" if days else "") + _quote(p))
    for r in model.get("replacement") or []:
        out.append(f"{_group_name(model, r['from'])} replaces the lowest {_group_name(model, r['to'])}" + _quote(r))
    for gate in model.get("gates") or []:
        out.append(f"Must reach {gate.get('min_percent', 60):g}% in {_group_name(model, gate['group'])} to pass"
                   + _quote(gate))
    for e in model.get("exams") or []:
        out.append(f"Exam: {e.get('title') or e.get('id')} at {e.get('at')}" + _quote(e))
    return out


def _group_name(model: dict, group_id: str) -> str:
    return next((g.get("name") or g["id"] for g in model["groups"] if g["id"] == group_id), group_id)


def _quote(rule: dict, key: str = "quote") -> str:
    return f' (syllabus: "{rule[key]}")' if rule.get(key) else " (no quote: assumption)"


def cmd_scan(args):
    state, log, _ = build_state(args)
    if nothing_due(state):
        fail("Nothing due in the plan window.", 5)
    plan = make_plan(state, log)
    payload = {"alert": report.is_alert(plan), "headline": report.headline(plan),
               "numbers": report.as_json(plan)["numbers"], "warnings": [w for w in plan.warnings if w]}
    text = report.headline(plan) + "".join(f"\n- {w}" for w in payload["warnings"])
    emit(args, payload, text)


def cmd_plan(args):
    state, log, previous = build_state(args)
    if nothing_due(state):
        fail("Nothing due in the plan window.", 5)
    plan = make_plan(state, log)
    out = Path(args.out) if args.out else (None if args.sample else store.default_plan_md())
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.markdown(plan), encoding="utf-8")
    if not args.sample:
        store.save_plan(report.saved(plan, previous))
    payload = report.as_json(plan)
    payload["plan_file"] = str(out) if out else None
    payload["updated_existing_plan"] = bool(previous)
    text = report.text(plan, out)
    if previous:
        text = f"(Updated your Red Alert plan from {previous['started'][:10]}.)\n" + text
    emit(args, payload, text)


def cmd_whatif(args):
    state, log, _ = build_state(args)
    if not args.skip and not args.score:
        fail("whatif needs --skip ID or --score ID=PCT", 2)
    before = make_plan(state, log)
    forced = {item_id: "skip" for item_id in args.skip or []}
    state2, _, _ = build_state(args)
    for spec in args.score or []:
        item_id, _, pct = spec.partition("=")
        try:
            set_score(state2, item_id, float(pct.rstrip("%")))
        except ValueError:
            fail(f"--score needs ID=PCT, like midterm2=75 (got {spec})", 2)
    after = make_plan(state2, log, forced)
    lines, rows = [], []
    for cid, p in after.projections.items():
        b = before.projections[cid]
        if abs(p["with_plan"] - b["with_plan"]) >= 0.05 or abs(p["if_everything"] - b["if_everything"]) >= 0.05:
            lines.append(f"{p['name']}: {b['letter_with_plan']} ({b['with_plan']:.1f}%) -> {p['letter_with_plan']} "
                         f"({p['with_plan']:.1f}%)")
            rows.append({"course_id": cid, "before": b["with_plan"], "after": p["with_plan"],
                         "letter_before": b["letter_with_plan"], "letter_after": p["letter_with_plan"]})
    old = {d.item.id: d for d in before.decisions}
    changes = []
    for d in after.decisions:
        o = old.get(d.item.id)
        if o and (o.verdict != d.verdict or abs(o.minutes - d.minutes) >= 30) and d.item.kind != "todo":
            changes.append({"id": d.item.id, "title": d.item.title, "before": o.verdict, "after": d.verdict,
                            "reason": report.reason(after, d)})
            lines.append(f"{d.item.title}: {o.verdict} -> {d.verdict}. {report.reason(after, d)}")
    freed = sum(o.minutes for o in before.decisions) - sum(d.minutes for d in after.decisions)
    if abs(freed) >= 15:
        lines.append(f"{'Frees' if freed > 0 else 'Costs'} {report.minutes(abs(freed))} of work.")
    if not lines:
        lines.append("No real difference: the plan and grades stay the same.")
    emit(args, {"grades": rows, "changes": changes, "freed_minutes": round(freed)}, "\n".join(lines))


def set_score(state, item_id: str, pct: float) -> None:
    item = next((i for i in state.items if i.id == item_id), None)
    if item is not None and item.course_id:
        state.courses[item.course_id].graded.append(
            {"item_id": item.id, "group": item.group, "score": item.points * pct / 100.0, "out_of": item.points})
        state.items = [i for i in state.items if i.id != item_id]
        return
    for course in state.courses.values():
        for exam in course.model.get("exams") or []:
            if exam.get("id") == item_id:
                points = float(exam.get("points") or 100)
                course.graded.append({"item_id": item_id, "group": exam["group"], "score": points * pct / 100.0,
                                      "out_of": points})
                return
    fail(f"Unknown item '{item_id}' for --score", 2)


def cmd_log(args):
    if args.sample:
        print(f"(sample) Logged {report.minutes(args.minutes)} for {args.item}. Nothing saved.")
        return
    plan = store.load_plan()
    item = ((plan or {}).get("items") or {}).get(args.item)
    if item is None:
        fail(f"'{args.item}' is not in the current Red Alert plan. Run plan first.", 2)
    log = store.load_effort()
    log.setdefault("entries", []).append({
        "item_id": args.item, "course_id": item.get("course_id"), "type": item.get("type"),
        "estimate_minutes": item.get("prior_minutes") or item.get("full_minutes"), "minutes": args.minutes,
        "done": bool(args.done), "at": datetime.now(timezone.utc).isoformat(),
    })
    store.save_effort(log)
    total = effort.logged_minutes(log, args.item)
    planned = item.get("full_minutes") or 0
    lines = [f"Logged {report.minutes(args.minutes)} on {item['title']} ({report.minutes(total)} so far"
             + (f", planned {report.minutes(planned)})." if planned else ").")]
    if args.done:
        lines.append("Marked done.")
    names = {}
    learned = effort.ratios(log)
    lines += effort.insights(learned, names)
    emit(args, {"item_id": args.item, "total_minutes": total, "done": bool(args.done),
                "insights": effort.insights(learned, names)}, "\n".join(lines))


def cmd_recap(args):
    plan = None if args.sample else store.load_plan()
    if args.sample:
        state, log, _ = build_state(args)
        plan = report.saved(make_plan(state, log))
        log = {"entries": []}
    else:
        log = store.load_effort()
    if not plan:
        fail("No Red Alert plan saved yet.", 5)
    items = plan["items"]
    done = set(effort.finished(log))
    graded = {k: v for k, v in items.items() if v["kind"] in ("graded", "attendance", "prep", "study")}
    handled = [k for k, v in graded.items() if v["verdict"] != "SKIP"]
    done_count = sum(1 for k in handled if k in done)
    skipped_value = sum(v["full_points"] for v in graded.values() if v["verdict"] == "SKIP")
    saved_minutes = sum(max(0, v["full_minutes"] - v["minutes"]) for v in items.values())
    text = (f"{done_count}/{len(handled)} planned items logged done. Skipped work worth {skipped_value:.1f} pt "
            f"in total. Saved ~{saved_minutes / 60:.0f} h vs doing everything in full.")
    emit(args, {"handled": len(handled), "done": done_count, "skipped_points": round(skipped_value, 2),
                "saved_hours": round(saved_minutes / 60, 1)}, text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Red Alert: what to do, shrink, shift or skip.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("course", "scan", "plan", "whatif", "log", "recap"):
        p = sub.add_parser(name)
        p.add_argument("--sample", action="store_true", help="use the bundled example; saved state is untouched")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if name in ("course", "scan", "plan", "whatif"):
            p.add_argument("--input", help="JSON file Cubbie wrote")
        if name == "course":
            p.add_argument("--save", action="store_true", help="save after the student confirmed the rules")
        if name == "plan":
            p.add_argument("--out", help="where to write the full plan as Markdown")
        if name == "whatif":
            p.add_argument("--skip", action="append", metavar="ID")
            p.add_argument("--score", action="append", metavar="ID=PCT")
        if name == "log":
            p.add_argument("--item", required=True)
            p.add_argument("--minutes", type=float, required=True)
            p.add_argument("--done", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        sys.exit(2 if exc.code else 0)
    handlers = {"course": cmd_course, "scan": cmd_scan, "plan": cmd_plan, "whatif": cmd_whatif, "log": cmd_log,
                "recap": cmd_recap}
    try:
        handlers[args.command](args)
    except InputError as exc:
        fail(str(exc), 2)
    except MissingCourse as exc:
        fail(f"No saved course model for: {', '.join(exc.course_ids)}. Read each syllabus, build the course model "
             "(references/course-model.md), confirm it with the student and run `course --input ... --save`.", 3)
    except CourseModelError as exc:
        fail(f"Course model problem: {exc}", 4)
    except store.StoreError as exc:
        fail(f"Saved Red Alert state is unreadable ({exc}). Start a fresh plan; the effort log is kept if it "
             "still reads.", 6)


if __name__ == "__main__":
    main()
