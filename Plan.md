# Red Alert: build plan

Built from [capabilities.md](capabilities.md). Every capability there maps to a part of this plan (see
"Capability map" at the end). Target: Cubbie Hackathon, Track 1 (a Cubbie Skill in a public GitHub repo).

## 1. Goal and definition of done

Red Alert is a Cubbie Skill. A student texts "red alert"; Cubbie gathers Canvas, the syllabus, Calendar, Gmail,
Google Tasks and memory; a Python script weighs every item and returns DO / SHRINK / SHIFT / SKIP decisions with
reasons; Cubbie texts tonight's plan, sends the full plan, and follows up.

Done for Track 1 when:

1. Cubbie installs the Skill from its GitHub link.
2. The main flow works on a real Cubbie account: "red alert" → syllabus rules confirmed → plan with reasons.
3. Follow-up works: a morning check-in logs real effort and re-plans.
4. The repo is public, with a README that shows the iMessage thread.
5. (Optional) a demo video on TikTok or Instagram.

## 2. Architecture: Cubbie understands, the script weighs

| Cubbie (the LLM, guided by `SKILL.md`) | The script (`scripts/redalert.py`) |
| --- | --- |
| Reads Canvas, syllabus, Calendar, Gmail, Tasks, memory | Never calls any service (scripts can't reach Cubbie's abilities) |
| Interprets syllabus fine print into a course model, with quotes | Validates the course model, flags gaps and contradictions |
| Classifies events (interview vs club social), asks when unsure | Computes grades, value per hour, cutoffs, study-hour split, late math |
| Writes the state file, runs the script | Fits work into free time, picks verdicts, writes reasons as facts |
| Turns the output into short texts, PDFs, Sheets, calendar blocks | Saves course models, effort log and the current plan under HOME |
| Asks for the student's yes before anything is sent or created | Learns effort ratios from logged actuals |

Data flow for one "red alert":

```
student: "red alert"
  → Cubbie: instant reply ("On it. Checking 5 courses, your calendar and inbox…")
  → Cubbie (background task): gather Canvas + syllabus + Calendar + Gmail + Tasks + memory
  → new course?  → Cubbie writes course.json → `redalert.py course` → validation + ambiguities
                 → Cubbie texts the rules summary, student confirms → saved
  → Cubbie writes state.json → `redalert.py plan` → verdicts, schedule, reasons, plan.md
  → Cubbie texts headline + tonight's top 3, sends plan.md as a PDF or Google Sheet
  → Cubbie offers: calendar blocks, morning check-in, reminders, weekly scan (each only after a yes)
```

## 3. Folder layout

```
red-alert/
  SKILL.md                      # what Cubbie follows (plain words, no tool names)
  capabilities.md               # product spec
  Plan.md                       # this file
  README.md                     # for voters and the gallery: pitch, screenshots, install link
  references/
    course-model.md             # how to turn a syllabus into the course model, with quotes
    state-format.md             # the state file Cubbie writes before scan / plan / whatif
    replies.md                  # message templates for every step
  scripts/
    redalert.py                 # CLI entry point, exit codes
    redalert_core/
      __init__.py
      store.py                  # paths under ~/.config/red-alert/, load/save, sample mode
      model.py                  # load + validate inputs, normalize times and time zones
      grades.py                 # course grade: weighted groups and total points, drops, replacement, gates
      effort.py                 # effort priors and learned ratios
      exams.py                  # study hours → expected score, exam-prep links
      timeplan.py               # free time, sleep floor, daily cap, slack, collisions, scheduling
      decide.py                 # option building, greedy upgrade, verdicts
      explain.py                # reason facts and short reason lines
      report.py                 # text output, plan.md, recap
  assets/
    sample_state.json           # the user's crunch scenario (Ed post, 8 h assignment, attendance, 2 midterms, project)
    sample_course_econ.json     # syllabus with drop-lowest, late penalty, gate, replacement rule
    sample_course_cs.json       # total-points course with participation points
  tests/
    test_grades.py
    test_decide.py
    test_timeplan.py
    test_cli.py
```

Python standard library only, compatible with Python 3.9+ (no `match`, no third-party packages), so `SKILL.md` has
no Setup step.

## 4. Data model

Full field lists go in `references/state-format.md` and `references/course-model.md`. Summary:

### 4.1 Course model (one per course, saved and reused)

```json
{
  "course_id": "econ201",
  "name": "ECON 201",
  "scheme": "weighted",
  "groups": [
    {"id": "hw", "name": "Homework", "weight": 15, "drop_lowest": 2,
     "quote": "Homework is 15% of your grade. The two lowest scores are dropped."},
    {"id": "mid", "name": "Midterms", "weight": 50},
    {"id": "final", "name": "Final", "weight": 35}
  ],
  "cutoffs": {"A": 93, "A-": 90, "B+": 87, "B": 83, "pass": 60, "quote": "..."},
  "late_policy": {"penalty_per_day": 10, "max_days": 3, "late_days_budget": 0, "quote": "..."},
  "participation": [{"kind": "attendance", "points_each": 0.2, "group": "part",
                     "recurs": "TU", "quote": "..."}],
  "replacement": [{"rule": "final_replaces_lowest", "group": "mid", "quote": "..."}],
  "gates": [{"group": "final", "min_percent": 60, "quote": "You must pass the final to pass the course."}],
  "extra_credit": [{"name": "Survey", "points": 1, "group": "hw", "quote": "..."}],
  "exams": [{"id": "econ_mid2", "name": "Midterm 2", "at": "2026-11-12T09:00-05:00", "group": "mid",
             "quote": "..."}],
  "ambiguities": ["Is the participation grade capped?"],
  "confirmed": true
}
```

`scheme` is `weighted` (by assignment group) or `points` (total points). Every rule carries `quote`: the exact
syllabus line. A rule without a quote is reported as an assumption.

### 4.2 State file (written by Cubbie before every run)

```json
{
  "now": "2026-11-02T22:40-05:00",
  "timezone": "America/New_York",
  "preferences": {"sleep_hours": 7.5, "daily_cap_hours": 9, "buffer_percent": 15,
                  "targets": {"econ201": "B+", "cs3500": "A"}},
  "courses": [{"course_id": "econ201", "graded": [{"item_id": "hw1", "score": 9, "out_of": 10}]}],
  "items": [{"id": "ed_post_w9", "course_id": "cs3500", "group": "part", "title": "Ed post week 9",
             "points": 1, "opens": "...", "due": "...", "available_until": "...",
             "type": "discussion", "submitted": false, "progress": 0, "group_project": false,
             "rubric": [{"part": "Section 4", "points": 5}], "prepares_for": [],
             "estimate_minutes": null}],
  "events": [{"id": "stripe_int", "title": "Stripe final round", "start": "...", "end": "...",
              "kind": "interview", "importance": "fixed", "prep_minutes": 120}],
  "busy": [{"start": "...", "end": "...", "title": "CS 3500 lecture"}],
  "todos": [{"title": "Laundry", "due": null, "estimate_minutes": 45}]
}
```

### 4.3 Saved state under `~/.config/red-alert/`

- `courses/<course_id>.json`: confirmed course models
- `effort.json`: logged actual minutes per item, with course and type
- `plan.json`: the current crunch plan (items, verdicts, progress), so a second "red alert" updates it
- `--sample` never reads or writes these (sample state stays in memory).

Same pattern as the kit's `examples/weather-before-class/scripts/forecast.py` (`settings_file`, `load_settings`,
`save_settings`, `SKILL_DATA_DIR` override).

## 5. The engine

### 5.1 Grades (`grades.py`)

- `course_grade(model, scores)` returns the course percentage for both schemes: weighted groups (each group's
  earned / possible, after drops, times its weight, normalized over groups with any possible points) and total
  points.
- Drops: within a group, drop the `drop_lowest` lowest percentages before summing.
- Replacement: "final replaces lowest midterm" applied when the final's percentage is higher.
- Gates: `gate_ok(model, scores)` checks min percentages; a failed gate means the course is failed whatever the
  total.
- Projection: ungraded items get the student's current average in that group (or course, if the group has none),
  stated as an assumption.
- **Item value by simulation, not formula**: `value(item) = grade(with item at expected score) − grade(with item at
  0 or late-penalized)`. This handles drops, replacement, extra credit and gates without special cases.
- Letter for a percentage from `cutoffs`; distance to the target letter's cutoff.

### 5.2 Cutoff-aware utility

Course points are converted to utility before comparing across courses:

- Within 3 points of the target cutoff (above or below): multiplier up to 3×, falling linearly to 1× at 3 points away.
- More than 5 points above the target: multiplier 0.5× (the course is safe).
- Projected below "pass" or a gate at risk: items in that course become **must-do** (cannot be SKIP).

Constants live in one place (`decide.py`) so they are easy to tune; reasons state the rule ("ECON is 0.4 from a B,
so its points count 3×").

### 5.3 Effort (`effort.py`)

- Priors by type (minutes): discussion 15, quiz 30, reading 60, problem set 240, lab report 300, essay per 1,000
  words 180, project milestone 480, attendance = the class length.
- Learned ratio per (course, type): average of actual / estimate over logged items, shrunk toward 1.0 with few
  samples (`ratio = (sum_actual + 2·prior_ratio·est) / (sum_est + 2·est)` style smoothing).
- Range: low = 0.7×, high = 1.4× the estimate; the plan uses the estimate, the headline shows the total range.
- `progress` (0–1) from the student reduces remaining effort.

### 5.4 Exams (`exams.py`)

- Expected exam score after h study hours: `s(h) = s0 + (smax − s0)(1 − e^(−h/τ))`; `s0` = current course average
  − 15 (floor 40), `smax` = min(100, current average + 10), `τ` = 4 h by default.
- Study is offered in 30-minute steps; the value of a step is the grade change from the score gain (through
  `grades.py`, so exam weight, replacement and gates are respected).
- Exam-prep links: an item with `prepares_for: [exam_id]` adds the value of the study time it replaces (half its
  effort counted as study for that exam), so a dropped homework that covers the midterm keeps value.

### 5.5 Time (`timeplan.py`)

- Free time = the window from `now` to the horizon (21 days) minus `busy`, `events` (plus prep and travel buffer),
  sleep (`sleep_hours` per night, default 23:30–07:00 shifted to fit), then minus `buffer_percent`, capped at
  `daily_cap_hours` per day.
- Slots of 30 minutes. Slack per item = free minutes before `due` − remaining effort of everything due before it.
- Collisions: two exams within 24 h, events overlapping busy blocks, deadlines inside an event.
- Scheduling: earliest deadline first into free slots; a task can split across slots unless marked not
  divisible; quick wins (≤ 15 min) go in the first slot.
- Feasibility check used by the decision step: does the chosen set fit before every deadline?

### 5.6 Decisions (`decide.py`)

1. Build options per item: full (DO), shrink levels (from the rubric: drop the parts with the lowest points per
   minute; without a rubric, default levels 60% effort → 85% score and 35% → 65%), late (SHIFT, one per allowed
   late day until `available_until`, with the penalty), skip.
2. Fixed first: events, interview prep blocks and protected items are placed, never traded.
3. Must-do floor: gated, fail-risk and exam-prep items start at their cheapest non-skip option; group projects are
   never SKIP or SHIFT, only flagged.
4. Greedy upgrade: start everything else at SKIP; repeatedly apply the upgrade (skip → shrink → full, or one more
   30-minute study step) with the best utility gain per hour that keeps the schedule feasible. Quick wins are
   upgraded first regardless.
5. If even the must-do floor doesn't fit: switch the cheapest must-do items to SHIFT where late is allowed, then
   report the shortfall honestly ("Even the essentials need 6 h more than you have").
6. Verdict = the final option: full → DO, partial → SHRINK, late or extension → SHIFT, none → SKIP. SHIFT also
   suggests an extension email draft when the syllabus allows extensions.

### 5.7 Reasons (`explain.py`)

Each verdict carries facts: minutes, points, utility multiplier, points per hour, hours until due, the rule applied
and its quote. `explain.py` renders one short line per verdict, for example
"Skip HW 5: 8 h for 0.5 pt (0.06 pt/h), and your lowest 2 HW are dropped." Cubbie may rephrase but must keep the
numbers.

### 5.8 Learning and recap

- `log --item <id> --minutes <n>` appends to `effort.json` and updates the plan's progress.
- When a ratio moves past 1.3 or below 0.75 with at least 3 samples, the output includes an insight line
  ("You underestimate CS labs by 40%. I've adjusted.").
- `recap` at the end of the crunch: items handled, value skipped, hours saved vs doing everything in full.

## 6. Script interface (`scripts/redalert.py`)

| Command | Does | Prints |
| --- | --- | --- |
| `course --input course.json` | Validates and saves a course model | Rules summary to confirm, ambiguities, missing quotes |
| `scan --input state.json` | Demand vs free time per week, next 21 days | Alert yes/no, the headline numbers |
| `plan --input state.json [--out plan.md]` | Full decision run; saves `plan.json` | Headline, tonight's top 3 with reasons, path of `plan.md` |
| `whatif --input state.json --skip <id>` / `--score <id>=<pct>` | Re-runs with a change | Grade and plan differences |
| `log --item <id> --minutes <n> [--done]` | Records actual effort | Updated remaining work, any insight |
| `recap` | End-of-crunch summary | Recap lines |
| any command `--sample` | Uses `assets/sample_*.json`, writes nothing | Same output |
| any command `--json` | Machine-readable output | JSON |

Output under 8,000 characters (Cubbie reads only that much); the full plan goes to `plan.md`.

Exit codes (mapped to replies in `SKILL.md`): 0 ok; 2 bad arguments or unreadable input file; 3 a course in the
state has no saved course model (run syllabus intake); 4 course model invalid (weights don't add up, cutoffs out
of order); 5 nothing due in the horizon; 6 saved state unreadable (start a fresh plan, keep the effort log).

## 7. `SKILL.md` outline

- **Frontmatter**: `name: red-alert`; `description`: first sentence under 200 characters, names the trigger
  ("red alert", "I'm drowning", "what should I do tonight") and how it differs from the built-in
  `study-plan-builder` (syllabus fine print, grade math, what to cut, learns effort).
- **When to use / not to use** (not for single-assignment reminders or drafting professor emails alone).
- **Steps**
  1. Instant acknowledgment, then work as a background task and text the result when ready.
  2. Check connections: Canvas missing → offer to connect and stop; Google missing → continue, say what is missing.
  3. Gather, in plain words: Canvas courses, assignments, groups and weights, grades, rubrics, submission status,
     due and available-until dates, announcements; each course's syllabus (Syllabus page, course pages, files);
     Calendar for the next 21 days; Gmail for interviews, meetings, deadline changes, extension replies; Google
     Tasks; memory for targets, sleep, protected events.
  4. Syllabus intake for any course without a saved model: build `course.json` per `references/course-model.md`,
     quoting every rule; run `course`; text the summary; save only after the student confirms.
  5. Classify events (interview, exam, class, meeting, social); ask once when importance is unclear.
  6. Ask once for anything started ("anything you're partway through?") and the targets if not remembered.
  7. Write `state.json` per `references/state-format.md`; run `plan`.
  8. Reply: headline, tonight's top 3 with reasons; send `plan.md` as a PDF or Google Sheet.
  9. Offer, one at a time, each created only after a yes: calendar blocks, a morning check-in during the crunch,
     reminders before key moments, extension email drafts, a weekly scan, a phone call for new alerts.
- **Follow-up flows**: morning check-in (ask what's done and how long, run `log`, re-run `plan`, send today's
  list); a second "red alert" (update, don't restart); what-if; weekly scan (`scan`, alert only on overload);
  recap when the last deadline passes. Scheduled check-ins are worded to make sense days later ("Red Alert
  morning check-in for the Nov 2–16 crunch: ask what got done, log it, re-plan").
- **Replies**: plain text, short, one idea per message, links on their own line, full plan in a document (see
  `references/replies.md`).
- **When something fails**: the exit-code table above, each with one actionable reply.
- **Guardrails**: never does graded work, never submits, never sends without a yes; safe side near cutoffs; states
  assumptions; data stays with the student.

## 8. Build order

Each step ends with a check.

0. **Cubbie spike test (before writing the engine).** On a real Cubbie, ask for assignment-group weights, a rubric,
   a course syllabus, available-until dates, and a background task plus a scheduled check-in.
   → check: write down what Cubbie can and can't see; adjust the course-model fallbacks (syllabus or asking the
   student) before step 1.
   **Result:** Cubbie reads assignment-group weights, rubrics and course syllabi. Not yet checked:
   available-until dates, background tasks, scheduled check-ins (covered in step 9).
1. **Data model + store**: `model.py`, `store.py`, the two reference files, the sample assets.
   → check: sample files load and validate; a broken course model exits 4.
2. **Grades**: `grades.py` for both schemes, drops, replacement, gates, projection.
   → check: `test_grades.py` (drop-lowest makes skipping the lowest cost ~0; replacement; a failed gate).
3. **Effort + exams**: priors, learned ratios, the study curve.
   → check: unit tests for smoothing and diminishing returns.
4. **Time**: free time, slack, collisions, EDF scheduling.
   → check: `test_timeplan.py` (sleep and daily cap respected, a 15-min item due in 24 h gets a slot).
5. **Decisions + reasons**: options, greedy upgrade, verdicts, `explain.py`.
   → check: `test_decide.py` on the user's scenario: Ed post DO first, Tuesday attendance DO, midterm study split
   by marginal hour, the 8 h / 0.5 pt assignment SHRINK or SKIP, the interview never moved, a group project only
   flagged, cutoff awareness moves hours to the course near a cutoff.
6. **CLI + report**: all commands, `--sample`, `--json`, exit codes, `plan.md`.
   → check: `test_cli.py`; `python scripts/redalert.py plan --sample` reads well and stays under 8,000 characters;
   with `HOME` set to a temp folder, `log` writes only there.
7. **SKILL.md + replies.md + README.md**.
   → check: `python ../cubbie-hackathon-kit/skills/cubbie-skill-creator/scripts/validate_cubbie_skill.py red-alert`
   shows no FAIL; every warning read.
8. **Publish** (only after the user's go-ahead): public GitHub repo, push, then `github_link.py red-alert` for the
   repository, branch and pinned links.
9. **Test on Cubbie** with the branch link: install, "red alert", syllabus confirmation, real plan, Canvas not
   connected, morning check-in and `log`, a second "red alert", what-if, weekly scan. Fix, push, text the link
   again, repeat.
10. **Demo video** (optional): 11 pm with six things due → "red alert" → headline → three reasoned decisions →
    calendar blocks → recap end card ("9/9 handled, saved 11 h").
11. **Submit** with `cubbie-hackathon-kit/skills/cubbie-hackathon/scripts/hackathon.py submit --track skills ...`:
    preview, show the user, send only on a clear yes.

MVP if time runs short: steps 0–7 with `course`, `plan` and `log`; `whatif`, `scan`, `recap` and the phone call
come after.

### Build status

Steps 0–7 are done: all six commands work, 42 tests pass (Python 3.14 and 3.11; every file parses as 3.9), and
the kit's structure check passes with no warnings. Next: step 8 (publish).

Changes from the design above, found while testing:

- **Replacement rules are only counted once the replacing exam is graded.** Counting on a future final at your
  average made studying for a midterm look worthless, which is unsafe advice.
- **Expected scores use the average of work handed in.** Zeros are usually missed work, so they no longer drag
  down what a completed post or homework is worth.
- **The headline measures the tightest deadline window**, not total work vs total free time, since a crunch is
  deadlines clustering.
- **Days run from waking to sleeping**, so late-night work counts toward that evening; daily caps are whole
  15-minute slots.
- **Interview prep is placed in the 48 hours before the interview.**
- **A class that clashes with a fixed or protected event is skipped**, with the clash as the reason.
- **With no target set, a letter within 1 point above counts as the target.**
- **Default daily cap is 6 h** (5 h in the sample).

## 9. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Canvas doesn't expose group weights or rubrics to Cubbie | Course model comes from the syllabus; rubric-less SHRINK uses default levels; step 0 finds out early |
| The LLM misreads fine print | Every rule quotes the syllabus; the student confirms once per course; validation catches weights that don't add up |
| Syllabus formats vary a lot | `references/course-model.md` has worked examples (table, prose, PDF); ambiguities are asked, not guessed |
| Overlap with the built-in `study-plan-builder` | Description states the differences; triggers on "red alert" |
| First run is slow | Instant reply, background task, saved course models |
| Advice to skip looks irresponsible | Must-do floor, safe side near cutoffs, exam-prep value, reasons with numbers, never does graded work |
| Bad effort estimates on first use | Priors plus progress questions; ranges shown; learning from day 1 |
| No real crunch to demo | Use a heavy real week, or add real items by text; sample mode only for local tests (Track 1 needs a real account) |
| Output too long for Cubbie | Text output capped; full plan in `plan.md` |

## 10. Capability map

| capabilities.md | Where it's built |
| --- | --- |
| Trigger, instant reply, background, update not restart | `SKILL.md` steps 1, 9; `plan.json` in `store.py` |
| 1. What it reads | `SKILL.md` step 3; `references/state-format.md` |
| 2. Syllabus fine print, quotes, confirm once, announcements | `references/course-model.md`; `course` command; `model.py` validation |
| 3. Time, slack, recurring items, collisions, headline | `timeplan.py`; `scan` and `plan` headline |
| 4. Value per hour, drops, cutoffs, projection, exams, late, non-grade | `grades.py`, `exams.py`, `decide.py` (utility) |
| 5. Verdicts with reasons, never-skip, group projects | `decide.py`, `explain.py` |
| 6. Plan, calendar blocks, interviews fixed + prep, reminders, check-in, what-if | `report.py`, `timeplan.py`, `whatif`, `SKILL.md` follow-up flows |
| 7. Weekly scan, phone call | `scan`; `SKILL.md` offers |
| 8. Learning, memory, recap | `effort.py`, `log`, `recap`; `SKILL.md` memory steps |
| 9. Guardrails | `SKILL.md` guardrails; `decide.py` must-do floor |
| 10. When something is missing | `SKILL.md` connection checks; exit codes |
| Requirements (no keys, stdlib only, differs from built-in) | Section 3 layout, frontmatter description |
