---
name: red-alert
description: Triages a crunch by weighing every assignment, exam, meeting and to-do by the grade it's worth per hour, then decides what to do, shrink, shift or skip, with reasons. Use when the student texts "red alert", says they're drowning, swamped, behind or panicking, asks what to do tonight or this week or what they can skip, or has several deadlines, midterms, projects or interviews landing within a few weeks. It reads each syllabus's fine print (weights, drop-lowest rules, late penalties, participation points, must-pass rules) and does exact grade math, which the built-in study-plan-builder does not; use it even if the student only says "help, everything is due".
---

# Red Alert

When everything is due at once, Red Alert decides what to do in full, what to shrink, what to hand in late
and what to skip, by the grade each hour earns, and tells the student why. Cubbie gathers and understands; the
script `scripts/redalert.py` does the math the same way every time. "pt" in its output means percentage points
of the course grade.

## When to use

- "red alert" (the main trigger; start right away, no questions first)
- "I'm drowning, 3 midterms and a project next week"
- "What should I do tonight?" / "What can I skip this week?"
- "What if I get a C on the midterm?" / "What if I skip the lab?"
- Morning check-ins and weekly scans this Skill scheduled

Do not use it for a single reminder about one deadline, for drafting a professor email on its own (that's
`email-to-professor`), or for a general study schedule with no trade-offs (that's `study-plan-builder`).

## 1. Reply right away, then work in the background

Text one line at once, naming what you'll check, for example: "On it. Checking 5 courses, your calendar and
inbox…". Then do the rest as a background task and text the result when it's ready. Never make the student
wait on a silent thread.

## 2. Check connections

- Canvas not connected: tell the student Red Alert needs Canvas, offer to connect it, and stop.
- Google not connected: continue with Canvas only, and say in the result what you couldn't see (meetings, free
  time, emails, to-dos).

## 3. Gather everything

Use the student's local date and time with its UTC offset as `now` (the sandbox clock may be in another zone).
Look 21 days ahead.

1. **Canvas**, for every active course: assignments with points, assignment group and group weight, due date,
   "available until" date, submission status and any rubric; current grades and each graded score; announcements
   from the last 2 weeks (moved deadlines, changed policies).
2. **Each course's syllabus** in Canvas: the Syllabus page, a course page, or an uploaded syllabus file. Search the
   course materials for it. Only courses without a saved course model need this (step 4).
3. **Google Calendar**: every event in the next 21 days (classes, meetings, office hours, shifts, interviews,
   exams, social plans).
4. **Gmail**: interview invites and times, meeting requests, deadline changes from professors or TAs, replies to
   extension requests. If an interview or meeting is in email but not on the calendar, include it and offer to add
   it to the calendar.
5. **Google Tasks**: open to-dos with due dates.
6. **Memory**: target grade per course, sleep time, daily work limit, protected events, anything the student is
   partway through.

## 4. Course models from the syllabus (first time per course)

The script needs each course's rules as a course model. Check for a saved one by running `plan` (step 6): exit
code 3 lists the courses that still need one. For each of those:

1. Read the syllabus and build the course model as described in `references/course-model.md`. Quote the exact
   syllabus line behind every rule. Cross-check weights against the Canvas assignment groups.
2. Save it as a file and check it: `python3 scripts/redalert.py course --input <course.json>`.
   Fix anything it reports as a problem (exit code 4) and re-run.
3. Text the student its one-line summary (it ends in "Right?") and ask the questions it lists, one at a time.
4. Only after the student confirms: `python3 scripts/redalert.py course --input <course.json> --save`.

When an announcement changes a rule or an exam date, update the course model, show the change, and save again
after the student confirms. Never invent a rule the syllabus doesn't state; when something isn't there, leave it
out and the script states the assumption.

## 5. Understand the rest

- **Classify every calendar or email event**: interview, exam, class, meeting, work shift, social. Interviews and
  other important meetings are `fixed` and get prep time (`prep_minutes`, usually 60–180). Events the student
  cares about are `protected`. If importance is unclear, ask once ("Is the club social a must?") and remember the
  answer.
- **Link work to exams**: an assignment or quiz that covers an upcoming exam's material gets that exam in
  `prepares_for`.
- **Ask once, with defaults the student can accept with "yes"**, only for what memory doesn't have:
  targets ("Any grade you're protecting? I'll assume you want to keep what you have."), anything started
  ("Anything you're partway through?"), sleep and daily limit ("Sleep 12:30–8 and max 6 h of work a day?").
  Remember the answers.
- **Estimates**: leave `estimate_minutes` empty unless the student or the assignment says how long it takes;
  the script uses typical times and learns the student's real ones.

## 6. Run the plan

Write the state file as described in `references/state-format.md`, for example to
`~/.config/red-alert/state.json`, then run from this Skill's folder:

```bash
python3 scripts/redalert.py plan --input ~/.config/red-alert/state.json
```

It prints the headline, the next work blocks with reasons, the cut decisions and grade projections, and writes the
full plan to `~/.config/red-alert/plan.md`. Add `--json` when you need every decision, block and reason as data
(for calendar blocks or a Sheet).

## 7. Reply

Follow `references/replies.md`. In short, as separate short texts:

1. The headline, as printed ("RED ALERT: 12 days, 13 deliverables, ~65 h of work, 56 free hours. You're 9 h
   over.").
2. Tonight's top 3, each with its reason and the numbers.
3. The cuts (SKIP, SHRINK, SHIFT), at most 3, each with its reason.
4. The full plan: turn `plan.md` into a PDF (or a Google Sheet if the student prefers) and send it with one line.
5. Anything under "Heads-up" (two exams within 24 h, a clash) and any assumption that matters.

Then offer, one at a time, and create each only after the student says yes:

- Work blocks on Google Calendar (from the `--json` blocks; leave fixed events alone).
- A morning check-in every day until the crunch ends (default 8:30 am).
- Reminders before key moments: interview prep, the night before each exam, deadlines about to close.
- An extension request email for any decision the output marks with an extension option (draft only; the student
  sends it).
- A message to group-project teammates when the plan flags a group project (draft only; the student sends it).
- A weekly scan (default Sunday 8 pm) to catch the next crunch early, optionally with a phone call when one starts.

## 8. Follow-ups

**Morning check-in** (scheduled). Word it so it makes sense on its own days later, for example: "Red Alert morning
check-in for the Nov 2–14 crunch: ask what got done yesterday and how long it took, log it, re-plan, and text
today's list." Then:

1. Ask what got done and how long it took (one question).
2. For each answer: `python3 scripts/redalert.py log --item <id> --minutes <n> [--done]`. Item ids are in the last
   `--json` output or `~/.config/red-alert/plan.json`.
3. Gather again (step 3, skipping syllabi), write the state file, run `plan`, and text today's list in 2–3 lines.
   Pass on any line the script prints about effort ("You underestimate CS labs by 40%. I've adjusted.").

**"red alert" again** during the same crunch: same as steps 3–7. The script keeps logged progress and says it
updated the existing plan; tell the student what changed.

**What-if**: `python3 scripts/redalert.py whatif --input <state.json> --score <id>=<percent>` or
`--skip <id>`. Exam ids come from the course models. Text the grade change and the plan changes it prints.

**Weekly scan** (scheduled, for example "Red Alert weekly scan: check the next 3 weeks for a crunch"): gather,
then `python3 scripts/redalert.py scan --input <state.json> --json`. If `alert` is false, send nothing (or one
calm line if the student asked for one). If it's true, text the headline and offer the full plan; call the
student if they chose a call for new alerts.

**Recap**: after the crunch's last deadline, `python3 scripts/redalert.py recap` and text its line ("9/9 planned
items logged done. Skipped work worth 0.6 pt in total. Saved ~11 h."). Then delete the morning check-in.

## Commands

| Command | Use |
| --- | --- |
| `course --input F [--save]` | Check a course model; save after the student confirms |
| `plan --input F [--out F] [--json]` | Decisions, schedule, reasons; saves the plan for follow-ups |
| `scan --input F [--json]` | Is a crunch coming? |
| `whatif --input F --skip ID` / `--score ID=PCT` | Consequences of a change |
| `log --item ID --minutes N [--done]` | Record real effort |
| `recap` | End-of-crunch summary |
| any of the above with `--sample` | Bundled example; reads and writes no saved state |

## Replies

Plain text, no Markdown, a few short lines per message, one idea per message, links on their own line. Lead with
the decision, then the reason with its numbers. Keep the script's numbers exactly; you may reword around them.
Long lists go in the plan document. Details and examples: `references/replies.md`.

## When something fails

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 2 | Bad arguments or a malformed state file | Fix the file using the message (it names the field) and run again; don't show the student the error |
| 3 | A course has no saved course model | Do step 4 for the courses it lists |
| 4 | A course model breaks a rule (weights don't add up, unknown group) | Re-read the syllabus, fix the model, ask the student if the syllabus itself is unclear |
| 5 | Nothing due in the next 21 days | Tell the student there's no crunch, and offer the weekly scan |
| 6 | Saved state unreadable | Tell the student you're starting a fresh plan; run `plan` again |

Never make up a plan, a grade or a number when the script fails.

## Guardrails

- Never do graded work for the student, never submit anything, never send an email or a message for them without
  their yes. Drafts only.
- Never skip what could make them fail: the script marks must-pass rules, at-risk courses, group projects and
  exam preparation as must-do. Don't override that.
- Interviews, exams and protected events are never moved or traded for points.
- State assumptions the script prints when weights, rules or grades were missing.
- Grades and plans stay in the student's own files under `~/.config/red-alert/`; nothing goes to any outside server.
