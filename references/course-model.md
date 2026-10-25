# Course model: turning a syllabus into rules

One JSON file per course, built by Cubbie from the syllabus (Canvas Syllabus page, a course page or the syllabus
file), checked with `python3 scripts/redalert.py course --input <file>` and saved with `--save` after the student
confirms. Saved models live in `~/.config/red-alert/courses/` and are reused.

**The one rule: quote the syllabus.** Every weight, cutoff and policy carries `quote`, the exact sentence it came
from. A rule you can't quote is an assumption: leave it out (the script uses a safe default and says so) or put
the question in `ambiguities`.

## Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `course_id` | yes | Same id used in the state file, for example the Canvas course id or "econ201" |
| `name` | yes | What the student calls it ("ECON 201") |
| `scheme` | yes | `weighted` (each group is a % of the grade) or `points` (grade = total points earned / total possible) |
| `groups` | yes | Grade components; see below |
| `cutoffs` | no | Letter → minimum percent, e.g. `{"A": 93, "A-": 90, "B+": 87}`; leave out if the syllabus has none |
| `cutoffs_quote` | with `cutoffs` | The grading-scale line |
| `pass_percent` | no | Minimum to pass the course; defaults to the lowest cutoff |
| `late_policy` | no | See below |
| `participation` | no | Recurring classes that earn points, see below |
| `replacement` | no | `[{"from": "final", "to": "mid", "quote": ...}]`: "the final replaces your lowest midterm" |
| `gates` | no | `[{"group": "final", "min_percent": 60, "quote": ...}]`: "you must pass the final to pass the course" |
| `exams` | no | `[{"id", "title", "group", "points", "at", "minutes", "study_hours", "quote"}]` |
| `ambiguities` | no | Questions for the student, e.g. "Is the participation grade capped at 100%?" |

### Groups

```json
{"id": "quiz", "name": "Quizzes", "weight": 16, "count": 8, "drop_lowest": 2,
 "quote": "Eight weekly quizzes make up 16%; your two lowest quiz scores are dropped."}
```

- `id`: short id; the same id goes in the state file's items (`group`).
- `weight`: percent of the course grade (weighted courses). Weights must add up to 100. A separate extra-credit
  bucket on top of 100% gets `"extra_credit": true`.
- `count`: how many items the group has over the whole term ("8 quizzes", "10 weekly posts"). Include it whenever
  the syllabus says; without it the value of each item is overestimated, and the script says so.
- `points_each`: typical points per item (points courses, or when no item in the group is known yet).
- `drop_lowest`: how many of the lowest scores are dropped.

Map Canvas assignment groups to these groups. If Canvas weights and the syllabus disagree, trust the syllabus,
mention it to the student, and quote the syllabus.

### Late policy

```json
{"accepts_late": true, "penalty_per_day": 10, "max_days": 3, "late_days_budget": 0, "extensions": "on request",
 "quote": "Late problem sets lose 10% per day and are not accepted after 3 days."}
```

- `accepts_late`: false when the syllabus says no late work.
- `penalty_per_day`: percent of the item's score lost per day late.
- `max_days`: last day late work is accepted.
- `late_days_budget`: free late days per term ("you get 3 late days, no questions asked").
- `extensions`: `on request` (ask the instructor), `none`, or leave out.

### Participation that repeats

```json
{"id": "cs_lecture", "title": "CS 3500 lecture", "group": "attend", "points_each": 1,
 "days": ["TU"], "start": "14:00", "minutes": 60, "quote": "Attendance is taken at every Tuesday lecture."}
```

`days` uses `MO TU WE TH FR SA SU`; `start` is local time. The script creates one item per class in the plan
window, so each lecture is weighed on its own. Weekly posts with a due date (discussion boards) are ordinary items
in the state file, not participation rules.

### Exams

Exams usually live in the syllabus schedule, the calendar or announcements, not the assignment list. Add every
dated exam with `at` (ISO time with offset), its `group` and `points`. `study_hours` is optional: the study time
that gets most of the benefit (default 8). If the calendar or an announcement moves an exam, pass the new time in
the state file's `exams` list instead of editing the model.

## Reading tips

| Syllabus says | Model |
| --- | --- |
| "Homework 25% (8 assignments, lowest dropped)" | group `hw`, weight 25, count 8, drop_lowest 1 |
| "Two midterms, 20% each" | group `mid`, weight 40, count 2 |
| "Participation: 10 weekly Ed posts, 1% each" | group `ed`, weight 10, count 10 |
| "Attendance 5% (25 lectures)" + "taken every Tuesday" | group `attend`, weight 5, count 25, plus a participation rule |
| "Grade = points out of 560" | scheme `points`, groups with `count` and `points_each` |
| "Final replaces your lowest midterm if higher" | replacement from `final` to `mid` |
| "You must pass the final to pass the course" | gate on `final`, min_percent 60 (or the stated minimum) |
| "No late work" | late_policy accepts_late false |
| "3 late days per semester" | late_policy late_days_budget 3 |
| "Lowest quiz dropped" | drop_lowest 1 on quizzes |
| A curve, "at the instructor's discretion" | leave out; add to `ambiguities` |

## Full example

```json
{
  "course_id": "econ201",
  "name": "ECON 201",
  "scheme": "weighted",
  "groups": [
    {"id": "ps", "name": "Problem sets", "weight": 4, "count": 8, "drop_lowest": 1,
     "quote": "Problem sets are worth 4% of the final grade (8 sets, lowest one dropped)."},
    {"id": "quiz", "name": "Quizzes", "weight": 16, "count": 8, "drop_lowest": 2,
     "quote": "Eight weekly quizzes make up 16%; your two lowest quiz scores are dropped."},
    {"id": "mid", "name": "Midterms", "weight": 40, "count": 2, "quote": "Two midterms, 20% each."},
    {"id": "final", "name": "Final exam", "weight": 35, "count": 1,
     "quote": "The cumulative final exam is 35% of your grade."},
    {"id": "part", "name": "Participation", "weight": 5, "count": 1,
     "quote": "Participation (in-class polls) counts for 5%."}
  ],
  "cutoffs": {"A": 93, "A-": 90, "B+": 87, "B": 83, "B-": 80, "C+": 77, "C": 73, "C-": 70, "D": 60},
  "cutoffs_quote": "A 93-100, A- 90-92.9, B+ 87-89.9, B 83-86.9, ...",
  "late_policy": {"accepts_late": true, "penalty_per_day": 10, "max_days": 3, "extensions": "on request",
                  "quote": "Late problem sets lose 10% per day and are not accepted after 3 days."},
  "replacement": [{"from": "final", "to": "mid",
                   "quote": "If your final exam score is higher than your lowest midterm, it replaces that midterm."}],
  "gates": [{"group": "final", "min_percent": 60,
             "quote": "You must score at least 60% on the final to pass the course."}],
  "exams": [{"id": "econ_mid2", "title": "ECON Midterm 2", "group": "mid", "points": 100,
             "at": "2026-11-12T09:00:00-05:00", "minutes": 75, "quote": "Midterm 2: Thursday, November 12."}],
  "ambiguities": []
}
```

More examples: `assets/sample_course_cs.json` (late-day budget, weekly lecture attendance) and
`assets/sample_course_psyc.json` (a total-points course).
