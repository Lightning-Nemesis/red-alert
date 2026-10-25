# Red Alert: capabilities

When everything is due at once, Red Alert decides what to do, what to shrink, what to shift and what to skip,
by the grade it's worth, and tells you why.

## Trigger

Text **"red alert"** to Cubbie. Red Alert starts checking everything right away and comes back with a plan.
Similar messages work too: "I'm drowning", "what should I do tonight?", "help me survive this week".

What happens:

1. Instant reply: "On it. Checking 5 courses, your calendar and inbox…"
2. Gathers everything in the background (see "What it reads").
3. First time only: texts a short summary of each course's syllabus rules to confirm once.
4. Sends the headline, tonight's top decisions with reasons, and the full plan as a PDF or Google Sheet.

Texting "red alert" again during the same crunch updates the existing plan; it keeps logged progress and does not
start over.

## 1. What it reads

| Source | What it uses |
| --- | --- |
| Canvas | Assignments, points, assignment groups and weights, current grades, rubrics, submission status, due and "available until" dates, announcements |
| Canvas syllabus | Every course's syllabus, found automatically: the Syllabus page, a course page or an uploaded syllabus file |
| Google Calendar | Classes, meetings, office hours, work shifts, exams, and real free time |
| Gmail | Interview invites, meeting requests, deadline changes from professors, replies to extension requests |
| Google Tasks | The student's own to-dos |
| Messages | Anything the student adds by text ("interview Thursday 2pm", "I'm halfway through the lab"); a syllabus photo or PDF as a fallback for a course not on Canvas |
| Memory | Target grade per course, sleep floor, protected events, saved course rules, effort history |

## 2. Understands the syllabus fine print

Turns each syllabus into rules it can calculate with, **quoting the syllabus line behind every rule**:

- Grade weights and letter cutoffs ("A ≥ 93")
- Weighted-by-group courses and total-points courses
- Drop rules ("lowest 2 quizzes dropped")
- Late policies ("−10% per day, max 3 days", "4 late days per semester")
- Participation ("0.2 points per class attended", "1 discussion post per week = 1 point")
- Replacement rules ("final replaces your lowest midterm")
- Gates ("you must pass the final to pass the course")
- Extra credit
- Exam dates, which usually live in the syllabus, calendar or announcements rather than the assignment list

Shows the rules once per course to confirm, for example: "ECON 201: midterms 25% each, final 35%, HW 15% (lowest 2
dropped), −10% per day late. Right?" Rules are saved and reused. A Canvas announcement that changes a rule or date
updates them. Anything it can't interpret, it asks about instead of guessing.

## 3. Understands time

- When each task opens, when it's due and when Canvas stops accepting it, in the student's time zone
- Recurring items ("every Tuesday class") count as repeating, each worth its own points
- Slack per task: time left minus work needed, so 24 hours left and a week left are weighed differently
- Real free time from the calendar, minus a sleep floor, a buffer and a daily cap on work hours
- Collisions: two exams on the same day, overlapping commitments
- The size of the crunch: "14 days, 9 deliverables, ~61 h of work, 38 free hours. You're 23 h over."

## 4. Weighs what each task is worth

A Python script does the math the same way every time:

- **Grade points per hour**: a 15-minute discussion post for 1 point (4.0 pt/h) beats a day-long assignment for
  0.5 points (0.06 pt/h)
- **Drop rules**: skipping the item that would be dropped anyway costs about 0
- **Cutoff awareness**: the student sets a target per course; points in a course 0.4 from dropping a letter count
  more than points in a course that's safe
- **Projected grades**: current grade plus an assumption for ungraded work (the student's average so far), stated
  out loud
- **Exam study by the hour**: each extra hour of studying earns less, so every hour goes to the exam or task that
  gains most from it
- **Exam preparation value**: a task that covers material for an upcoming exam keeps value even when its own points
  are small or dropped
- **Late penalties**: compares turning it in late against rushing it or skipping it
- **Non-grade items**: interviews, meetings and protected events are never traded for points

## 5. Decides, with reasons

Every item gets a verdict and a one-line reason with the numbers behind it:

- **DO**: "Post on the discussion board tonight: 15 min for 1 pt, closes in 22 h."
- **SHRINK**: "Lab report: do sections 1–3 fully. Section 4 is worth 5/100, so write one paragraph."
- **SHIFT**: "Ask for a 2-day extension on the project (I drafted the email), or take the −10% late penalty."
- **SKIP**: "Skip HW 5: 8 h for 0.5 pt, and your lowest homework is dropped."

Never SKIP: anything that could make the student fail, gated items, or work needed for an upcoming exam.
Group projects are flagged rather than skipped or shifted, with a drafted message to teammates the student sends.

## 6. Plans and keeps adjusting

- Tonight's plan by text; the full 2–3 week plan as a PDF or Google Sheet
- Work and study blocks on Google Calendar, after the student says yes
- Interviews and important meetings are fixed: never moved or traded for points, with a prep block before each one
- Reminders before key moments (interview prep, the night before an exam, deadlines about to close), after the
  student says yes
- Morning check-in during the crunch: "Did you finish X? How long did it take?", then a re-plan around what slipped
- What-if answers: "What if I get a C on the midterm?", "What if I skip the lab?" show the grade and plan
  consequences instantly

## 7. Watches ahead (optional)

- A weekly scan of the next 3 weeks at a time the student picks (for example Sunday 8 pm)
- Raises a Red Alert when the work is more than the free time, optionally with a phone call

## 8. Learns the student

- Records how long things actually took and adjusts future estimates: "You underestimate CS labs by 40%. I've
  adjusted."
- Remembers targets, sleep floor, protected events and course rules across conversations
- Recap when the crunch ends: "9/9 handled. Skipped work worth 0.6%. Saved 11 h."

## 9. Guardrails

- Never does graded work, never submits, never sends an email without the student's yes
- Plays it safe when a grade is close to a cutoff
- States every assumption when weights, rules or grades are missing
- Grades and plans stay with the student; nothing goes to any outside server

## 10. When something is missing

- Canvas not connected: says so, offers to connect it, and stops
- Google not connected: plans from Canvas only and says what it couldn't see (meetings, free time, emails)
- No syllabus found for a course: asks for a photo or PDF, or plans that course from Canvas weights with the
  assumption stated
- Nothing heavy coming up: says so and offers the weekly scan

## Requirements

- Sign-in: only Canvas and Google, already connected to Cubbie. No extra keys or accounts.
- Scripts: Python standard library only, so there is no setup step.
- Different from Cubbie's built-in study planner: Red Alert reads syllabus fine print, does the grade math, decides
  what to cut, and learns the student's real effort.
