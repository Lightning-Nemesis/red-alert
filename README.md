# Red Alert 🚨

**When everything is due at once, Red Alert tells you what to do, what to shrink, and what to skip, by the grade
it's worth.** A [Cubbie](https://cubbie.ai) Skill for the Cubbie Hackathon.

Text Cubbie **"red alert"**. It reads your Canvas courses, every syllabus's fine print, your calendar, inbox and
to-dos, then weighs each hour of work by the grade it earns:

```text
RED ALERT: 12 days, 13 deliverables, ~65 h of work, 56 free hours. You're 9 h over.

Tonight:
1. 10:45 PM Ed post week 9: 15 min for 0.9 pt (3.6 pt/h), due in 21 h. Quick win.
2. 11 PM Reading response 8: 30 min for 0.7 pt.

Skip Problem Set 6: 8 h for 0.06 pt, and the lowest problem set score is dropped.
Study 10 h for ECON Midterm 2: worth 4.3 pt. ECON is 1.1 above the B+ line, so its points count 2.25x.
Skip the Nov 10 CS lecture: it clashes with the career fair, which comes first.
```

## Install

Text this link to Cubbie and reply "yes":

```text
https://github.com/Lightning-Nemesis/red-alert
```

Then text "red alert". It needs Canvas connected to Cubbie; Google (Calendar, Gmail, Tasks) makes it sharper. No
other accounts or keys.

## What it does

- **Reads the fine print.** Weights, letter cutoffs, "lowest 2 quizzes dropped", "−10% per day late", "3 late
  days", "0.2% per lecture attended", "final replaces your lowest midterm", "you must pass the final". It quotes
  the syllabus line behind every rule and confirms each course once.
- **Does the grade math.** Each task's value comes from recomputing your course grade with and without it, so
  drop rules and replacement rules count. Points near a letter cutoff count more than points in a course you're
  safe in.
- **Understands time.** 24 hours left vs a week left, recurring lectures, sleep, a daily work limit, interviews and
  events that can't move, two exams in one day.
- **Decides with reasons.** DO, SHRINK (with the rubric parts to go light on), SHIFT (late penalty or late days,
  or an extension request it drafts) or SKIP, each with the minutes, points and points per hour.
- **Studies smart.** Each extra study hour earns less, so hours go to the exam that gains most from the next one.
- **Keeps up.** Morning check-ins re-plan around what slipped, "what if I get a C on the midterm?" answers, a
  weekly scan that warns you before the next crunch, and a recap when it's over.
- **Learns you.** Logs how long things really take: "You underestimate CS labs by 40%. I've adjusted."
- **Safe by design.** Never does graded work, never submits or sends anything without your yes, never skips what
  could fail you, never counts on a future exam to bail you out. Your data stays in your own Cubbie files.

## How it works

Cubbie does the reading and understanding (Canvas, syllabi, calendar, email) and writes it to a file.
`scripts/redalert.py`, plain Python with no packages, does the weighing: course grades as the syllabus computes
them, value per hour, a schedule that fits before every deadline, and the DO/SHRINK/SHIFT/SKIP decisions.

```text
SKILL.md                     what Cubbie follows
references/                  syllabus → rules, the data format, reply style
scripts/redalert.py          course | plan | scan | whatif | log | recap
scripts/redalert_core/       grades, effort, exams, time, decisions, reasons
assets/sample_*.json         a full example crunch (three courses)
tests/                       42 tests, including the "15-minute post vs day-long assignment" case
```

Try it without Cubbie:

```bash
python3 scripts/redalert.py plan --sample
python3 scripts/redalert.py whatif --sample --score econ_mid2=72
python -m unittest discover -s tests
```
