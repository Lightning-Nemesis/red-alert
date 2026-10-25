"""Exam study with diminishing returns: each extra hour earns less than the one before.

Expected score after h hours: s(h) = s0 + (smax - s0) * (1 - e^(-h / tau)). The baseline comes from the
student's average in the course, so a strong student gains less per hour than one who is behind.
"""

from __future__ import annotations

import math

TAU_HOURS = 4.0  # hours until about 63% of the possible gain is captured
STEP_MINUTES = 30
PREP_CREDIT = 0.5  # share of a linked item's time that counts as study for its exam


def curve(average: float) -> tuple:
    """(s0, smax) as fractions for a course average given as a fraction."""
    s0 = max(0.40, min(0.95, average - 0.15))
    smax = min(1.0, max(s0 + 0.05, average + 0.10))
    return s0, smax


def expected_score(average: float, study_hours: float) -> float:
    s0, smax = curve(average)
    return s0 + (smax - s0) * (1 - math.exp(-max(study_hours, 0.0) / TAU_HOURS))


def full_study_hours(exam) -> float:
    """Study that captures most of the gain (about 86%), unless the syllabus or student says otherwise."""
    return float(exam.study_hours) if exam.study_hours else 2 * TAU_HOURS
