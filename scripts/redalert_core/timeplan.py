"""Free time and scheduling.

Time from now to the horizon is cut into 15-minute slots. Classes, meetings, interviews, exams and sleep are
blocked; each day keeps a buffer and a cap on work hours. Work is placed earliest deadline first, which also
answers the question the decision step keeps asking: does this set of work fit before every deadline?
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from datetime import datetime, time, timedelta

SLOT = 15  # minutes


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


class Calendar:
    def __init__(self, state):
        self.state = state
        prefs = state.prefs
        first = state.now.replace(second=0, microsecond=0)
        first += timedelta(minutes=(-first.minute) % SLOT)
        self.slots = []
        t = first
        while t < state.horizon_end:
            self.slots.append(t)
            t += timedelta(minutes=SLOT)
        self.sleep = self._sleep_windows(prefs)
        fixed = [i for i in state.items if i.kind in ("attendance", "exam") and i.start]
        attendance = [i for i in fixed if i.kind == "attendance"]
        blocks = [(e.start, e.end) for e in state.events]
        blocks += [(i.start, i.end) for i in fixed if i.kind == "exam"]
        for start, end, _ in state.busy:
            # A class that earns attendance points is represented by its item, so skipping it frees the time.
            if not any(_overlaps(start, end, a.start, a.end) for a in attendance):
                blocks.append((start, end))
        blocks += self.sleep
        blocks.sort()
        self.base_blocked = [False] * len(self.slots)
        for idx, s in enumerate(self.slots):
            e = s + timedelta(minutes=SLOT)
            for b_start, b_end in blocks:
                if b_start >= e:
                    break
                if _overlaps(s, e, b_start, b_end):
                    self.base_blocked[idx] = True
                    break
        self.item_slots = {
            i.id: [idx for idx, s in enumerate(self.slots)
                   if _overlaps(s, s + timedelta(minutes=SLOT), i.start, i.end)]
            for i in attendance
        }
        # A student's day runs from waking up to going to sleep, so late-night work counts toward that evening.
        hh, mm = (int(x) for x in str(prefs["sleep_start"]).split(":")[:2])
        wake = (timedelta(hours=hh, minutes=mm) + timedelta(hours=float(prefs["sleep_hours"]))) % timedelta(days=1)
        self.day = [(s - wake).date() for s in self.slots]
        free_by_day = defaultdict(int)
        for idx, blocked in enumerate(self.base_blocked):
            if not blocked:
                free_by_day[self.day[idx]] += SLOT
        cap = float(prefs["daily_cap_hours"]) * 60
        keep = 1 - float(prefs["buffer_percent"]) / 100.0
        self.cap = {d: SLOT * int(min(cap, free * keep) // SLOT) for d, free in free_by_day.items()}

    def _sleep_windows(self, prefs) -> list:
        hh, mm = (int(x) for x in str(prefs["sleep_start"]).split(":")[:2])
        hours = float(prefs["sleep_hours"])
        out = []
        day = self.state.now.date() - timedelta(days=1)
        last = self.state.horizon_end.date() + timedelta(days=1)
        while day <= last:
            start = datetime.combine(day, time(hh, mm), tzinfo=self.state.tz)
            if hh < 12:  # "01:00" means after midnight
                start += timedelta(days=1)
            out.append((start, start + timedelta(hours=hours)))
            day += timedelta(days=1)
        return out

    def tonight_end(self) -> datetime:
        """When the student's current evening ends: the next sleep window."""
        for start, end in self.sleep:
            if end > self.state.now:
                return max(start, self.state.now)
        return self.state.horizon_end

    def capacity(self, until: datetime, attended=()) -> float:
        """Usable work minutes from now until `until`, after sleep, blocks, buffer and daily caps."""
        blocked = {idx for item_id in attended for idx in self.item_slots.get(item_id, [])}
        used = defaultdict(float)
        total = 0.0
        for idx, s in enumerate(self.slots):
            if s + timedelta(minutes=SLOT) > until:
                break
            if self.base_blocked[idx] or idx in blocked:
                continue
            day = self.day[idx]
            take = min(SLOT, self.cap.get(day, 0) - used[day])
            if take > 0:
                used[day] += take
                total += take
        return total

    def schedule(self, tasks: list, attended=(), quick_first=False) -> tuple:
        """Place tasks earliest deadline first.

        tasks: [{"id", "minutes", "release", "deadline"}]. Returns (shortfall minutes, blocks, late ids) where
        blocks are [{"id", "start", "end", "minutes"}] and late ids are tasks that couldn't finish in time.
        """
        blocked = {idx for item_id in attended for idx in self.item_slots.get(item_id, [])}
        remaining = {t["id"]: float(t["minutes"]) for t in tasks if t["minutes"] > 0}
        pending = sorted((t for t in tasks if t["id"] in remaining),
                         key=lambda t: t["release"] or self.state.now)
        heap, assigned, late = [], [], []
        used = defaultdict(float)
        nxt = 0
        for idx, s in enumerate(self.slots):
            if self.base_blocked[idx] or idx in blocked:
                continue
            end = s + timedelta(minutes=SLOT)
            while nxt < len(pending) and (pending[nxt]["release"] or self.state.now) <= s:
                t = pending[nxt]
                urgent = t["deadline"] - self.state.now <= timedelta(hours=48)
                quick = 0 if quick_first and t["minutes"] <= SLOT and urgent else 1
                heapq.heappush(heap, (quick, t["deadline"], t["id"]))
                nxt += 1
            day = self.day[idx]
            room = min(SLOT, self.cap.get(day, 0) - used[day])
            while room > 1e-9 and heap:
                _, deadline, tid = heap[0]
                if deadline < end:
                    heapq.heappop(heap)
                    late.append(tid)
                    continue
                take = min(room, remaining[tid])
                assigned.append((s + timedelta(minutes=SLOT - room), tid, take))
                remaining[tid] -= take
                room -= take
                used[day] += take
                if remaining[tid] <= 1e-9:
                    heapq.heappop(heap)
            if nxt >= len(pending) and not heap:
                break
        late += [tid for _, _, tid in heap]
        late += [t["id"] for t in pending[nxt:]]
        shortfall = sum(remaining[tid] for tid in set(late))
        return shortfall, self._blocks(assigned), sorted(set(late))

    @staticmethod
    def _blocks(assigned: list) -> list:
        blocks = []
        for start, tid, minutes in assigned:
            end = start + timedelta(minutes=minutes)
            if blocks and blocks[-1]["id"] == tid and blocks[-1]["end"] == start:
                blocks[-1]["end"] = end
                blocks[-1]["minutes"] += minutes
            else:
                blocks.append({"id": tid, "start": start, "end": end, "minutes": minutes})
        return blocks


def collisions(state) -> list:
    """Plain-language warnings: exams close together, events on top of exams or classes."""
    out = []
    exams = sorted((i for i in state.items if i.kind == "exam"), key=lambda i: i.start)
    for a, b in zip(exams, exams[1:]):
        if (b.start - a.start) <= timedelta(hours=24):
            out.append(f"{a.title} and {b.title} are within 24 h of each other.")
    fixed = [(i.title, i.start, i.end) for i in state.items if i.kind in ("exam", "attendance") and i.start]
    for event in state.events:
        for title, start, end in fixed:
            if _overlaps(event.start, event.end, start, end):
                out.append(f"{event.title} overlaps {title}.")
    return out
