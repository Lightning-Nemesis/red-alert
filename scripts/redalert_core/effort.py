"""How long things take: priors by task type, corrected by what the student actually logged."""

from __future__ import annotations

# Minutes for a typical item of each type, before anything is learned.
PRIORS = {
    "discussion": 15,
    "attendance": 60,
    "quiz": 30,
    "reading": 60,
    "assignment": 180,
    "problem_set": 240,
    "lab": 240,
    "lab_report": 300,
    "essay": 360,
    "project": 480,
    "presentation": 240,
    "todo": 45,
    "prep": 60,
}
PSEUDO_SAMPLES = 2  # how strongly the prior holds before real samples outweigh it
INSIGHT_MIN_SAMPLES = 3


def prior_minutes(item) -> tuple:
    """(minutes, source) before learning: the student's or Cubbie's estimate, else the type prior."""
    if item.estimate_minutes:
        return float(item.estimate_minutes), "given"
    if item.start and item.end:
        return (item.end - item.start).total_seconds() / 60.0, "fixed"
    return float(PRIORS.get(item.type, PRIORS["assignment"])), "prior"


def _key(course_id, item_type) -> str:
    return f"{course_id or '-'}|{item_type}"


def finished(log: dict) -> dict:
    """{item_id: (course_id, type, estimate, total minutes)} for items logged as done."""
    per_item = {}
    for entry in log.get("entries") or []:
        row = per_item.setdefault(entry["item_id"], {"minutes": 0.0, "done": False, "entry": entry})
        row["minutes"] += float(entry.get("minutes") or 0)
        row["done"] = row["done"] or bool(entry.get("done"))
    return {item_id: (r["entry"].get("course_id"), r["entry"].get("type"), float(r["entry"].get("estimate_minutes")
                                                                                  or 0), r["minutes"])
            for item_id, r in per_item.items() if r["done"]}


def logged_minutes(log: dict, item_id: str) -> float:
    return sum(float(e.get("minutes") or 0) for e in log.get("entries") or [] if e.get("item_id") == item_id)


def ratios(log: dict) -> dict:
    """{course|type: (ratio, samples)} from finished items: actual / estimated, pulled toward 1.0."""
    sums = {}
    for course_id, item_type, est_minutes, actual_minutes in finished(log).values():
        if not est_minutes:
            continue
        key = _key(course_id, item_type)
        actual, est, n = sums.get(key, (0.0, 0.0, 0))
        sums[key] = (actual + actual_minutes, est + est_minutes, n + 1)
    out = {}
    for key, (actual, est, n) in sums.items():
        mean_est = est / n
        out[key] = ((actual + PSEUDO_SAMPLES * mean_est) / (est + PSEUDO_SAMPLES * mean_est), n)
    return out


def estimate(item, learned: dict) -> tuple:
    """(full minutes, prior minutes, ratio) for an item; fixed-time items are never rescaled."""
    minutes, source = prior_minutes(item)
    if source == "fixed" or item.kind in ("study", "exam", "attendance"):
        return minutes, minutes, 1.0
    ratio, _ = learned.get(_key(item.course_id, item.type), (1.0, 0))
    return minutes * ratio, minutes, ratio


def insights(learned: dict, course_names: dict) -> list:
    lines = []
    for key, (ratio, n) in sorted(learned.items()):
        if n < INSIGHT_MIN_SAMPLES:
            continue
        course_id, item_type = key.split("|", 1)
        what = f"{course_names.get(course_id, course_id)} {item_type.replace('_', ' ')}s"
        if ratio >= 1.3:
            lines.append(f"You underestimate {what} by {round((ratio - 1) * 100)}%. I've adjusted.")
        elif ratio <= 0.75:
            lines.append(f"{what} take you {round((1 - ratio) * 100)}% less time than planned. I've adjusted.")
    return lines
