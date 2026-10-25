# State file: what Cubbie hands the script

Written fresh before every `plan`, `scan` or `whatif` run (for example to `~/.config/red-alert/state.json`).
Times are ISO 8601 with the student's UTC offset (`2026-11-05T23:59:00-05:00`). Ids must stay the same between
runs (use Canvas ids where there are any) so logged progress lines up. A full example is
`assets/sample_state.json`.

## Top level

| Field | Required | Meaning |
| --- | --- | --- |
| `now` | yes | The student's local date and time, with offset |
| `timezone` | no | IANA name, e.g. `America/New_York` (helps across daylight-saving changes) |
| `preferences` | no | See below |
| `courses` | yes | One entry per active course with a course model |
| `items` | yes | Assignments, quizzes, posts, projects (not exams: those come from the course models) |
| `exams` | no | Exam dates found in the calendar or announcements that differ from (or are missing in) the course model |
| `events` | no | Interviews, meetings, career fairs, social plans: anything with a fixed time |
| `busy` | no | Other blocked time: classes, shifts, commutes |
| `todos` | no | Google Tasks and to-dos the student mentioned |

## preferences

```json
{"sleep_start": "00:30", "sleep_hours": 7.5, "daily_cap_hours": 6, "buffer_percent": 15, "horizon_days": 21,
 "targets": {"econ201": "B+", "cs3500": "A"}}
```

All optional. Defaults: sleep 23:30 for 7.5 h, at most 6 h of work a day, 15% of free time kept as a buffer, 21
days. `targets` maps course ids to the letter the student wants to protect or reach; without one, the plan protects
the letter they hold (or one within a point above).

## courses

```json
{"course_id": "econ201", "current_percent": 86.9, "late_days_left": 2,
 "graded": [{"item_id": "ps1", "group": "ps", "score": 9, "out_of": 10}]}
```

- `graded`: every graded score from Canvas, with its group. Include zeros.
- `current_percent`: Canvas's current grade (used only when nothing is graded yet).
- `late_days_left`: when the course has a late-day budget and Canvas or the student knows how many are left.

## items

```json
{"id": "ps6", "course_id": "econ201", "group": "ps", "title": "Problem Set 6", "type": "problem_set",
 "points": 10, "due": "2026-11-05T23:59:00-05:00", "available_until": "2026-11-08T23:59:00-05:00",
 "opens": null, "submitted": false, "progress": 0, "estimate_minutes": null,
 "rubric": [{"part": "Q1", "points": 3}, {"part": "Q4 (bonus graph)", "points": 2}],
 "prepares_for": ["econ_mid2"], "group_project": false, "must_do": false, "url": "https://canvas..."}
```

| Field | Meaning |
| --- | --- |
| `id`, `title`, `course_id`, `group`, `points` | From Canvas; `group` is the course model's group id |
| `type` | `discussion`, `quiz`, `reading`, `assignment`, `problem_set`, `lab`, `lab_report`, `essay`, `project`, `presentation` (sets the typical time) |
| `due`, `available_until`, `opens` | Canvas due, "available until" (lock) and "available from" dates |
| `submitted` | true items are left out |
| `progress` | 0–1, what the student said is already done ("halfway" = 0.5) |
| `estimate_minutes` | Only if the student or the assignment gives one |
| `rubric` | Canvas rubric rows: `part`, `points`, optional `minutes` |
| `prepares_for` | Exam ids this item covers |
| `group_project`, `must_do` | true when it's a group project, or the student says it must be done |
| `start`, `end` | Only for graded things at a fixed time (a lab section with points); they're weighed like attendance |
| `url` | Link to show the student |

Leave out items due after the plan window. Past-due items only belong here if Canvas still accepts them
(`available_until` in the future).

## exams (optional updates)

```json
{"id": "econ_mid2", "at": "2026-11-12T09:00:00-05:00"}
```

Same fields as the course model's exams; a matching `id` overrides the model (a moved exam), a new `id` with a
`course_id` and `group` adds one.

## events

```json
{"id": "stripe", "title": "Stripe SWE intern final round", "start": "2026-11-06T11:00:00-05:00",
 "end": "2026-11-06T12:00:00-05:00", "kind": "interview", "importance": "fixed", "prep_minutes": 180}
```

- `kind`: interview, meeting, career, work, social, exam, other.
- `importance`: `fixed` (can't move: interviews, appointments), `protected` (the student wants it), `optional`.
  Fixed and protected events are never traded for points; a class that clashes with one is skipped.
- `prep_minutes`: prep time to place in the 48 hours before it (interviews: 60–180).

## busy

```json
{"title": "ECON 201 lecture", "start": "2026-11-04T10:00:00-05:00", "end": "2026-11-04T10:50:00-05:00"}
```

Classes, shifts, commutes and other calendar blocks that aren't events above. Classes that earn attendance points
can stay here too; the script recognizes them from the course model.

## todos

```json
{"id": "rent", "title": "Pay rent", "due": "2026-11-05T23:59:00-05:00", "estimate_minutes": 15, "must_do": true}
```

To-dos have no grade value: they fill time grade work doesn't need, unless `must_do` is true.
