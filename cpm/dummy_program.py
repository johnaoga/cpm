"""Generate a skeleton (dummy) programme from a ScheduleConfig.

The dummy programme contains all time-slots (sessions, breaks, lunch, dinner,
preliminary/reserved slots) but no papers, rooms, or chairs assigned yet.
Session IDs are generated so they can be referenced in subsequent constraints.
"""

from __future__ import annotations

from .config import ScheduleConfig
from .models import (
    Constraint,
    DayProgram,
    Program,
    Session,
    SlotKind,
    TimeSlot,
)


def _minutes(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _build_day_slots(
    cfg: ScheduleConfig,
    day: int,
    session_counter: list[int],
) -> list[dict]:
    """Build the list of time-slot dicts for one day.

    Returns a list of slot dicts:
      {"time_slot": TimeSlot, "sessions": [Session, ...]}
    """
    start = _minutes(cfg.effective_day_start(day))
    end = _minutes(cfg.effective_day_end(day))

    # Collect preliminary slots for this day, sorted by start time
    prelims = sorted(
        [ps for ps in cfg.preliminary_slots if ps.day == day],
        key=lambda ps: _minutes(ps.start),
    )

    # Collect constraints that fix a session label
    fixed_labels: dict[str, str] = {}
    for c in cfg.constraints:
        if c.subject_type == "section" and c.op.value == "=" and c.value:
            fixed_labels[c.subject_id] = c.value[0]

    slots: list[dict] = []
    cursor = start
    prelim_idx = 0

    # Place breaks and lunch at conventional clock times.
    # Find when regular sessions actually begin (after contiguous opening prelims).
    eff_start = start
    for ps in prelims:
        ps_start = _minutes(ps.start)
        ps_end = _minutes(ps.end)
        # Only count prelims that start within room_change_penalty of current eff_start
        if ps_start <= eff_start + cfg.room_change_penalty_min:
            eff_start = ps_end
        else:
            break

    # If effective start is already past 10:30, skip morning break entirely
    can_morning = cfg.morning_break and eff_start < _minutes("10:30")
    morning_break_target = _minutes("10:30") if can_morning else end + 1
    lunch_target = max(_minutes("12:00"), eff_start + 80)
    afternoon_break_target = max(_minutes("15:00"), lunch_target + cfg.lunch_duration_min + 80)

    placed_morning_break = not can_morning
    placed_lunch = not cfg.lunch_included
    placed_afternoon_break = not cfg.afternoon_break

    while cursor + cfg.presentation_duration_min <= end:
        # Check if a preliminary slot starts here (or before the next session)
        if prelim_idx < len(prelims):
            ps = prelims[prelim_idx]
            ps_start = _minutes(ps.start)
            ps_end = _minutes(ps.end)
            if ps_start <= cursor + cfg.room_change_penalty_min:
                # Insert the preliminary slot
                ts = TimeSlot(
                    start=_fmt(ps_start),
                    end=_fmt(ps_end),
                    kind=SlotKind.PRELIMINARY,
                    label=ps.label,
                    day=day,
                )
                sid = f"P{day}_{prelim_idx + 1}"
                sess = Session(
                    session_id=sid,
                    day=day,
                    time_slot=ts,
                    label=ps.label,
                    is_fixed=True,
                )
                slots.append({"time_slot": ts, "sessions": [sess]})
                cursor = ps_end
                prelim_idx += 1
                continue

        # Morning break
        if not placed_morning_break and cursor >= morning_break_target:
            ts = TimeSlot(
                start=_fmt(cursor),
                end=_fmt(cursor + cfg.break_duration_min),
                kind=SlotKind.BREAK,
                label="Morning Break",
                day=day,
            )
            slots.append({"time_slot": ts, "sessions": []})
            cursor += cfg.break_duration_min
            placed_morning_break = True
            continue

        # Lunch
        if not placed_lunch and cursor >= lunch_target:
            ts = TimeSlot(
                start=_fmt(cursor),
                end=_fmt(cursor + cfg.lunch_duration_min),
                kind=SlotKind.LUNCH,
                label="Lunch",
                day=day,
            )
            slots.append({"time_slot": ts, "sessions": []})
            cursor += cfg.lunch_duration_min
            placed_lunch = True
            continue

        # Afternoon break
        if not placed_afternoon_break and cursor >= afternoon_break_target:
            ts = TimeSlot(
                start=_fmt(cursor),
                end=_fmt(cursor + cfg.break_duration_min),
                kind=SlotKind.BREAK,
                label="Afternoon Break",
                day=day,
            )
            slots.append({"time_slot": ts, "sessions": []})
            cursor += cfg.break_duration_min
            placed_afternoon_break = True
            continue

        # Regular session slot
        sess_end = min(cursor + cfg.max_session_duration_min, end)
        # Don't overshoot into the next preliminary
        if prelim_idx < len(prelims):
            ps_start = _minutes(prelims[prelim_idx].start)
            sess_end = min(sess_end, ps_start)

        if sess_end - cursor < cfg.presentation_duration_min:
            cursor = sess_end
            continue

        ts = TimeSlot(
            start=_fmt(cursor),
            end=_fmt(sess_end),
            kind=SlotKind.SESSION,
            label="",
            day=day,
        )
        n_papers = (sess_end - cursor) // cfg.presentation_duration_min

        # Create parallel sessions (one per room available)
        sessions: list[Session] = []
        rooms_this_day = min(cfg.num_available_rooms, cfg.max_rooms_per_day)
        for r in range(rooms_this_day):
            session_counter[0] += 1
            sid = f"S{session_counter[0]:02d}"
            label = fixed_labels.get(sid, "")
            is_fixed = sid in fixed_labels
            sess = Session(
                session_id=sid,
                day=day,
                time_slot=ts,
                label=label,
                is_fixed=is_fixed,
            )
            sessions.append(sess)

        slots.append({"time_slot": ts, "sessions": sessions})
        cursor = sess_end

    # Dinner (after day_end if included)
    if cfg.dinner_included:
        dinner_start = _minutes(cfg.dinner_start)
        dinner_end = dinner_start + 120  # 2 hours default
        ts = TimeSlot(
            start=_fmt(dinner_start),
            end=_fmt(dinner_end),
            kind=SlotKind.DINNER,
            label="Conference Dinner",
            day=day,
        )
        slots.append({"time_slot": ts, "sessions": []})

    return slots


def generate_dummy_program(cfg: ScheduleConfig) -> Program:
    """Create a skeleton programme respecting the schedule configuration."""
    counter = [0]  # mutable counter shared across days
    days: list[DayProgram] = []
    for d in range(1, cfg.num_days + 1):
        day_slots = _build_day_slots(cfg, d, counter)
        days.append(DayProgram(day=d, slots=day_slots))

    meta = {
        "num_days": cfg.num_days,
        "presentation_duration_min": cfg.presentation_duration_min,
        "max_session_duration_min": cfg.max_session_duration_min,
        "papers_per_session": cfg.papers_per_session,
        "generated": "dummy",
    }
    return Program(days=days, metadata=meta)
