"""Post-output manual programme editing operations.

All operations work on a :class:`Program` object loaded from JSON,
mutate it in-place, and return it so the caller can save it back.

Operations intentionally skip constraint validation — they are meant
for quick human-driven tweaks after the automated pipeline has run.
"""

from __future__ import annotations

import logging
from typing import Optional

from .models import (
    Chair,
    Paper,
    Program,
    Session,
    SlotKind,
    TimeSlot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time arithmetic helpers
# ---------------------------------------------------------------------------

def _parse_hhmm(t: str) -> int:
    """Convert ``"HH:MM"`` to minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _format_hhmm(minutes: int) -> str:
    """Convert minutes since midnight back to ``"HH:MM"``."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _slot_duration_min(ts: "TimeSlot") -> int:
    """Elapsed minutes of a time-slot."""
    return _parse_hhmm(ts.end) - _parse_hhmm(ts.start)


def _max_papers_in_slot(slot: dict) -> int:
    """Return the maximum paper count across sessions in *slot*."""
    return max((len(s.papers) for s in slot.get("sessions", []) if s.papers), default=0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_session(program: Program, session_id: str) -> Optional[tuple[Session, dict, int]]:
    """Return (session, slot_dict, day) for *session_id*, or None."""
    for dp in program.days:
        for slot in dp.slots:
            for sess in slot.get("sessions", []):
                if sess.session_id == session_id:
                    return sess, slot, dp.day
    return None


def _all_sessions(program: Program) -> list[tuple[Session, TimeSlot, int]]:
    """Yield (session, timeslot, day) for every SESSION slot."""
    result = []
    for dp in program.days:
        for slot in dp.slots:
            ts = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue
            for sess in slot["sessions"]:
                result.append((sess, ts, dp.day))
    return result


def _all_chairs(program: Program) -> dict[int, Chair]:
    """Collect every Chair object currently assigned in the programme."""
    chairs: dict[int, Chair] = {}
    for sess, _ts, _day in _all_sessions(program):
        if sess.chair:
            chairs[sess.chair.chair_id] = sess.chair
    return chairs


def _unassigned_chairs(
    program: Program,
    all_chairs: list[Chair],
) -> list[Chair]:
    """Return chairs from *all_chairs* not currently assigned to any session."""
    assigned_ids = {ch.chair_id for ch in _all_chairs(program).values()}
    return [ch for ch in all_chairs if ch.chair_id not in assigned_ids]


def _recalc_timeslots(program: Program) -> None:
    """Re-derive per-session TimeSlot start/end from slot ordering.

    After swapping or moving sessions the individual session TimeSlot
    objects keep stale values.  This helper walks the programme and
    copies the parent slot's TimeSlot into each session.
    """
    for dp in program.days:
        for slot in dp.slots:
            ts: TimeSlot = slot["time_slot"]
            for sess in slot.get("sessions", []):
                if sess.time_slot is not None:
                    sess.time_slot = TimeSlot(
                        start=ts.start,
                        end=ts.end,
                        kind=ts.kind,
                        label=ts.label,
                        day=ts.day,
                        chair=ts.chair,
                        speaker=ts.speaker,
                    )


# ---------------------------------------------------------------------------
# Swap two sessions (exchange positions including rooms)
# ---------------------------------------------------------------------------

def swap_sessions(program: Program, id_a: str, id_b: str) -> Program:
    """Swap sessions *id_a* and *id_b* in the programme.

    Exchanges the two sessions' positions in their respective slots
    (including room assignments).  Time-slots are updated to match
    the new positions.
    """
    res_a = _find_session(program, id_a)
    res_b = _find_session(program, id_b)
    if res_a is None:
        raise ValueError(f"Session {id_a!r} not found")
    if res_b is None:
        raise ValueError(f"Session {id_b!r} not found")

    sess_a, slot_a, _day_a = res_a
    sess_b, slot_b, _day_b = res_b

    # Find indices within session lists
    idx_a = next(i for i, s in enumerate(slot_a["sessions"]) if s.session_id == id_a)
    idx_b = next(i for i, s in enumerate(slot_b["sessions"]) if s.session_id == id_b)

    # Swap in lists
    slot_a["sessions"][idx_a] = sess_b
    slot_b["sessions"][idx_b] = sess_a

    _recalc_timeslots(program)
    logger.info("Swapped sessions %s ↔ %s", id_a, id_b)
    return program


# ---------------------------------------------------------------------------
# Slot-level helpers
# ---------------------------------------------------------------------------

def _parse_slot_ref(program: Program, ref: str) -> Optional[tuple[int, int]]:
    """Resolve a slot reference to ``(day_idx, slot_idx)``.

    Accepted formats:
      - ``"day:index"`` e.g. ``"1:3"`` → day 1, slot index 3 (0-based)
      - any *session_id* contained in the slot  (e.g. ``"P1_3"``, ``"TueA01"``)
    """
    # Try day:index notation first
    if ":" in ref:
        parts = ref.split(":", 1)
        try:
            day_num, si = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        for di, dp in enumerate(program.days):
            if dp.day == day_num:
                if 0 <= si < len(dp.slots):
                    return di, si
                return None
        return None

    # Fall back to session_id lookup
    for di, dp in enumerate(program.days):
        for si, slot in enumerate(dp.slots):
            for sess in slot.get("sessions", []):
                if sess.session_id == ref:
                    return di, si
    return None


def _session_slot_index(program: Program, session_id: str) -> Optional[tuple[int, int, int]]:
    """Return (day_idx, slot_idx, sess_idx_in_slot) for *session_id*."""
    for di, dp in enumerate(program.days):
        for si, slot in enumerate(dp.slots):
            ts = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue
            for sei, sess in enumerate(slot["sessions"]):
                if sess.session_id == session_id:
                    return di, si, sei
    return None


def _adjacent_session_slot(program: Program, day_idx: int, slot_idx: int,
                           direction: int) -> Optional[int]:
    """Find next SESSION-type slot in *direction* (+1 or -1) on same day."""
    dp = program.days[day_idx]
    idx = slot_idx + direction
    while 0 <= idx < len(dp.slots):
        if dp.slots[idx]["time_slot"].kind == SlotKind.SESSION:
            return idx
        idx += direction
    return None


# ---------------------------------------------------------------------------
# Move a session up or down (swap with adjacent SESSION slot)
# ---------------------------------------------------------------------------

def move_session(program: Program, session_id: str, direction: str) -> Program:
    """Move session *session_id* up or down by one slot.

    *direction* must be ``"up"`` or ``"down"``.  The session swaps
    with the session occupying the same position index in the
    adjacent SESSION slot on the same day.
    """
    loc = _session_slot_index(program, session_id)
    if loc is None:
        raise ValueError(f"Session {session_id!r} not found")
    day_idx, slot_idx, sess_idx = loc

    delta = -1 if direction == "up" else 1
    adj = _adjacent_session_slot(program, day_idx, slot_idx, delta)
    if adj is None:
        raise ValueError(f"No adjacent session slot {direction} from {session_id}")

    dp = program.days[day_idx]
    other_sessions = dp.slots[adj]["sessions"]
    # Pick same positional index, clamped
    other_idx = min(sess_idx, len(other_sessions) - 1)
    other_id = other_sessions[other_idx].session_id

    return swap_sessions(program, session_id, other_id)


# ---------------------------------------------------------------------------
# Move an entire slot up or down (works for plenary, break, session, …)
# ---------------------------------------------------------------------------

def move_slot(
    program: Program,
    slot_ref: str,
    direction: str,
    presentation_duration_min: int = 20,
) -> Program:
    """Swap the entire slot identified by *slot_ref* with its neighbour.

    *slot_ref* can be a ``"day:index"`` string (e.g. ``"1:3"``) or any
    session_id within the slot (e.g. ``"P1_3"``).

    *direction* must be ``"up"`` or ``"down"``.

    Slot durations are preserved and all start/end times for the day
    are recomputed.  Gaps between consecutive slots are kept.
    The last slot in a day is extended to the original day-end time;
    when that slot moves away from the last position its intrinsic
    duration is ``max_papers × presentation_duration_min``.
    """
    loc = _parse_slot_ref(program, slot_ref)
    if loc is None:
        raise ValueError(f"Slot {slot_ref!r} not found")
    day_idx, slot_idx = loc
    dp = program.days[day_idx]
    n = len(dp.slots)

    delta = -1 if direction == "up" else 1
    adj = slot_idx + delta
    if adj < 0 or adj >= n:
        raise ValueError(
            f"Cannot move slot {slot_ref} {direction} — already at the edge"
        )

    # ── 1. Snapshot the day's timing structure ──────────────────────────
    day_end = _parse_hhmm(dp.slots[-1]["time_slot"].end)   # anchor
    day_start = _parse_hhmm(dp.slots[0]["time_slot"].start)  # anchor

    # Intrinsic duration per slot (minutes)
    durations: list[int] = []
    for i, slot in enumerate(dp.slots):
        ts = slot["time_slot"]
        dur = _slot_duration_min(ts)
        # Last slot may have been extended to day_end; use paper count
        if i == n - 1:
            mp = _max_papers_in_slot(slot)
            if mp > 0:
                paper_dur = mp * presentation_duration_min
                if paper_dur < dur:
                    dur = paper_dur
        durations.append(dur)

    # Gaps between consecutive slots (minutes)
    gaps: list[int] = []
    for i in range(n - 1):
        end_i = _parse_hhmm(dp.slots[i]["time_slot"].end)
        start_next = _parse_hhmm(dp.slots[i + 1]["time_slot"].start)
        gaps.append(max(start_next - end_i, 0))

    # ── 2. Swap slots and their durations ──────────────────────────────
    dp.slots[slot_idx], dp.slots[adj] = dp.slots[adj], dp.slots[slot_idx]
    durations[slot_idx], durations[adj] = durations[adj], durations[slot_idx]
    # Gaps stay at their *positional* indices (between position i and i+1)

    # ── 3. Recompute all start/end times from day_start ────────────────
    cursor = day_start
    for i, slot in enumerate(dp.slots):
        ts: TimeSlot = slot["time_slot"]
        ts.start = _format_hhmm(cursor)
        if i == n - 1:
            # Last slot extends to day_end
            ts.end = _format_hhmm(max(cursor + durations[i], day_end))
        else:
            ts.end = _format_hhmm(cursor + durations[i])
            cursor = cursor + durations[i] + gaps[i]

    _recalc_timeslots(program)

    label_moved = dp.slots[adj]["time_slot"].label or ",".join(
        s.session_id for s in dp.slots[adj].get("sessions", [])
    )
    label_other = dp.slots[slot_idx]["time_slot"].label or ",".join(
        s.session_id for s in dp.slots[slot_idx].get("sessions", [])
    )
    logger.info("Moved slot [%s] %s (swapped with [%s])", label_moved, direction, label_other)
    return program


# ---------------------------------------------------------------------------
# List all slots (compact overview)
# ---------------------------------------------------------------------------

def list_slots(program: Program) -> list[dict]:
    """Return a compact list of all slots for display."""
    rows: list[dict] = []
    for dp in program.days:
        for si, slot in enumerate(dp.slots):
            ts: TimeSlot = slot["time_slot"]
            sess_ids = [s.session_id for s in slot.get("sessions", [])]
            rows.append({
                "day": dp.day,
                "index": si,
                "ref": f"{dp.day}:{si}",
                "time": f"{ts.start}-{ts.end}",
                "kind": ts.kind.value,
                "label": ts.label,
                "sessions": ", ".join(sess_ids) if sess_ids else "",
            })
    return rows


# ---------------------------------------------------------------------------
# Merge two sessions
# ---------------------------------------------------------------------------

def merge_sessions(program: Program, id_keep: str, id_remove: str) -> Program:
    """Merge *id_remove* into *id_keep*.

    Papers from *id_remove* are appended to *id_keep*.
    *id_remove* is then deleted from its slot.
    """
    res_keep = _find_session(program, id_keep)
    res_rm = _find_session(program, id_remove)
    if res_keep is None:
        raise ValueError(f"Session {id_keep!r} not found")
    if res_rm is None:
        raise ValueError(f"Session {id_remove!r} not found")

    sess_keep, _slot_keep, _day_keep = res_keep
    sess_rm, slot_rm, _day_rm = res_rm

    sess_keep.papers.extend(sess_rm.papers)
    slot_rm["sessions"] = [s for s in slot_rm["sessions"] if s.session_id != id_remove]
    logger.info(
        "Merged session %s into %s (%d papers total)",
        id_remove, id_keep, len(sess_keep.papers),
    )
    return program


# ---------------------------------------------------------------------------
# Swap chairs between two sessions
# ---------------------------------------------------------------------------

def swap_chairs(program: Program, id_a: str, id_b: str) -> Program:
    """Swap the chair assignments of sessions *id_a* and *id_b*."""
    res_a = _find_session(program, id_a)
    res_b = _find_session(program, id_b)
    if res_a is None:
        raise ValueError(f"Session {id_a!r} not found")
    if res_b is None:
        raise ValueError(f"Session {id_b!r} not found")

    sess_a = res_a[0]
    sess_b = res_b[0]
    sess_a.chair, sess_b.chair = sess_b.chair, sess_a.chair
    logger.info(
        "Swapped chairs: %s now has %s, %s now has %s",
        id_a, sess_a.chair.name if sess_a.chair else "(none)",
        id_b, sess_b.chair.name if sess_b.chair else "(none)",
    )
    return program


# ---------------------------------------------------------------------------
# Replace a chair
# ---------------------------------------------------------------------------

def replace_chair(
    program: Program,
    session_id: str,
    new_chair: Chair,
) -> Program:
    """Replace the chair of *session_id* with *new_chair*."""
    res = _find_session(program, session_id)
    if res is None:
        raise ValueError(f"Session {session_id!r} not found")
    sess = res[0]
    old_name = sess.chair.name if sess.chair else "(none)"
    sess.chair = new_chair
    logger.info(
        "Replaced chair of %s: %s → %s", session_id, old_name, new_chair.name,
    )
    return program


# ---------------------------------------------------------------------------
# Suggest unassigned chairs (by topic closeness)
# ---------------------------------------------------------------------------

def suggest_chairs(
    program: Program,
    session_id: str,
    all_chairs: list[Chair],
    papers: Optional[list] = None,
    top_n: int = 10,
) -> list[tuple[Chair, float]]:
    """Return up to *top_n* unassigned chairs ranked by topic affinity.

    If *papers* is provided, chair topic_ids are inferred from author
    matches (same logic as ``assign_chairs``).

    Each entry is ``(Chair, score)`` where a higher score means better
    topic match.
    """
    # Infer topic_ids from papers if available
    if papers:
        from .assign_chairs import _infer_chair_topics
        _infer_chair_topics(all_chairs, papers)

    res = _find_session(program, session_id)
    if res is None:
        raise ValueError(f"Session {session_id!r} not found")
    sess, _slot, day = res
    topic_id = sess.topic.topic_id if sess.topic else -1

    # Collect all topic_ids in this session's papers as secondary match
    sess_pref_ids: set[int] = set()
    for p in sess.papers:
        sess_pref_ids.update(p.pref_ids)

    unassigned = _unassigned_chairs(program, all_chairs)
    scored: list[tuple[Chair, float]] = []
    for ch in unassigned:
        # Exclude chairs not available on session day
        if day < ch.arrival_day or day > ch.departure_day:
            continue
        score = 0.0
        if topic_id >= 0 and topic_id in ch.topic_ids:
            score += 100.0
        # Secondary: overlap between chair topics and session paper prefs
        if ch.topic_ids and sess_pref_ids:
            overlap = len(set(ch.topic_ids) & sess_pref_ids)
            score += overlap * 10.0
        scored.append((ch, score))

    scored.sort(key=lambda x: (-x[1], x[0].name))
    return scored[:top_n]


# ---------------------------------------------------------------------------
# List sessions (compact overview for the user)
# ---------------------------------------------------------------------------

def list_sessions(program: Program) -> list[dict]:
    """Return a compact list of sessions for display."""
    rows = []
    for sess, ts, day in _all_sessions(program):
        rows.append({
            "session_id": sess.session_id,
            "day": day,
            "time": f"{ts.start}-{ts.end}",
            "topic": sess.topic.name if sess.topic else "",
            "room": sess.room.name if sess.room else "",
            "chair": sess.chair.name if sess.chair else "",
            "papers": len(sess.papers),
        })
    return rows


# ---------------------------------------------------------------------------
# Paper-level operations
# ---------------------------------------------------------------------------

def _find_paper(
    program: Program, paper_id: int,
) -> Optional[tuple[Session, int, dict, int]]:
    """Return (session, paper_index, slot_dict, day) for *paper_id*."""
    for dp in program.days:
        for slot in dp.slots:
            for sess in slot.get("sessions", []):
                for pi, p in enumerate(sess.papers):
                    if p.paper_id == paper_id:
                        return sess, pi, slot, dp.day
    return None


def move_paper(
    program: Program,
    paper_id: int,
    direction: Optional[str] = None,
    to_session: Optional[str] = None,
) -> Program:
    """Move paper *paper_id* up/down within its session, or to another session.

    If *to_session* is given, the paper is removed from its current session
    and appended to the target session.  Otherwise *direction* (``"up"`` or
    ``"down"``) reorders the paper within its current session.
    """
    res = _find_paper(program, paper_id)
    if res is None:
        raise ValueError(f"Paper {paper_id} not found in any session")
    sess, pi, _slot, _day = res

    if to_session is not None:
        target = _find_session(program, to_session)
        if target is None:
            raise ValueError(f"Session {to_session!r} not found")
        target_sess = target[0]
        paper = sess.papers.pop(pi)
        target_sess.papers.append(paper)
        logger.info(
            "Moved paper %d from %s to %s", paper_id, sess.session_id, to_session,
        )
        return program

    if direction is None:
        raise ValueError("Either --direction or --to-session is required for move-paper")

    if direction == "up":
        if pi == 0:
            raise ValueError(f"Paper {paper_id} is already first in session {sess.session_id}")
        sess.papers[pi], sess.papers[pi - 1] = sess.papers[pi - 1], sess.papers[pi]
    else:
        if pi >= len(sess.papers) - 1:
            raise ValueError(f"Paper {paper_id} is already last in session {sess.session_id}")
        sess.papers[pi], sess.papers[pi + 1] = sess.papers[pi + 1], sess.papers[pi]

    logger.info(
        "Moved paper %d %s in session %s", paper_id, direction, sess.session_id,
    )
    return program


def add_paper(
    program: Program,
    session_id: str,
    paper: Paper,
) -> Program:
    """Add *paper* to *session_id*.

    If the paper already exists in the programme it is moved (removed
    from its current session first).
    """
    # Remove from current session if already present
    existing = _find_paper(program, paper.paper_id)
    if existing is not None:
        old_sess, old_pi, _slot, _day = existing
        old_sess.papers.pop(old_pi)
        logger.info("Removed paper %d from %s before adding to %s",
                    paper.paper_id, old_sess.session_id, session_id)

    target = _find_session(program, session_id)
    if target is None:
        raise ValueError(f"Session {session_id!r} not found")
    target[0].papers.append(paper)
    logger.info("Added paper %d (%s) to session %s",
                paper.paper_id, paper.title[:40], session_id)
    return program


def swap_papers(program: Program, paper_a: int, paper_b: int) -> Program:
    """Swap two papers (possibly in different sessions)."""
    res_a = _find_paper(program, paper_a)
    res_b = _find_paper(program, paper_b)
    if res_a is None:
        raise ValueError(f"Paper {paper_a} not found")
    if res_b is None:
        raise ValueError(f"Paper {paper_b} not found")

    sess_a, pi_a, _slot_a, _day_a = res_a
    sess_b, pi_b, _slot_b, _day_b = res_b

    sess_a.papers[pi_a], sess_b.papers[pi_b] = sess_b.papers[pi_b], sess_a.papers[pi_a]
    logger.info(
        "Swapped paper %d (%s) ↔ paper %d (%s)",
        paper_a, sess_a.session_id, paper_b, sess_b.session_id,
    )
    return program
