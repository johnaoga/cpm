"""Assign rooms to sessions in an existing programme.

Strategy:
  - Plenary / fixed sessions without a room → largest-capacity room.
  - Regular sessions → assign rooms by topic popularity (more papers = bigger
    room).  Maintain topic→room continuity across consecutive slots.
  - Respect room-day constraints from the config.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from .config import ScheduleConfig
from .models import (
    ConstraintOp,
    Paper,
    Program,
    Room,
    Session,
    SlotKind,
)

logger = logging.getLogger(__name__)


def _parse_room_constraints(cfg: ScheduleConfig) -> dict[str, list[int]]:
    """Extract room-day constraints: room_name -> allowed days."""
    room_days: dict[str, list[int]] = {}
    for c in cfg.constraints:
        if c.subject_type != "room":
            continue
        room_name = c.subject_id
        days: list[int] = []
        for v in c.value:
            if v.startswith("day_"):
                try:
                    days.append(int(v.split("_")[1]))
                except (IndexError, ValueError):
                    pass
        if c.op in (ConstraintOp.EQ, ConstraintOp.IN) and days:
            room_days[room_name] = days
    return room_days


def _topic_popularity(papers: list[Paper]) -> dict[int, int]:
    """Count how many papers list each topic as a preference."""
    pop: dict[int, int] = defaultdict(int)
    for p in papers:
        for tid in p.pref_ids:
            pop[tid] += 1
    return dict(pop)


def _session_popularity(sess: Session, topic_pop: dict[int, int]) -> int:
    """Estimate audience size for a session based on its topic and papers."""
    # If already has papers, count them
    if sess.papers:
        return len(sess.papers)
    # Otherwise use topic popularity
    if sess.topic:
        return topic_pop.get(sess.topic.topic_id, 0)
    return 0


def assign_rooms(
    program: Program,
    rooms: list[Room],
    cfg: ScheduleConfig,
    papers: Optional[list[Paper]] = None,
) -> Program:
    """Assign rooms to every session slot in *program*.

    When room capacity data is available:
      - Plenary / fixed sessions get the largest available room.
      - Regular sessions are ranked by topic popularity (papers count)
        and matched to rooms by descending capacity.

    Modifies the programme in-place and returns it.
    """
    room_day_constraints = _parse_room_constraints(cfg)
    topic_pop = _topic_popularity(papers) if papers else {}

    # Sort rooms by capacity descending (largest first)
    rooms_sorted = sorted(rooms, key=lambda r: r.capacity, reverse=True)

    # For each day, track topic→room assignment for continuity
    prev_topic_room: dict[int, Room] = {}

    for day_prog in program.days:
        day = day_prog.day
        available = [
            r for r in rooms_sorted
            if r.name not in room_day_constraints
            or day in room_day_constraints[r.name]
        ]
        if not available:
            available = list(rooms_sorted)

        for slot in day_prog.slots:
            ts = slot["time_slot"]

            # Plenary / fixed slots → assign largest available room
            if ts.kind == SlotKind.PLENARY:
                sessions: list[Session] = slot.get("sessions", [])
                for sess in sessions:
                    if sess.room is None and available:
                        sess.room = available[0]  # largest capacity
                continue

            if ts.kind != SlotKind.SESSION:
                continue

            sessions = slot["sessions"]
            used_rooms: set[int] = set()

            # First pass: honour topic→room continuity
            for sess in sessions:
                if sess.topic and sess.topic.topic_id in prev_topic_room:
                    candidate = prev_topic_room[sess.topic.topic_id]
                    if candidate.room_id not in used_rooms and candidate in available:
                        sess.room = candidate
                        used_rooms.add(candidate.room_id)

            # Second pass: rank unassigned sessions by popularity,
            # then pair with largest remaining rooms
            unassigned = [s for s in sessions if s.room is None]
            unassigned.sort(
                key=lambda s: _session_popularity(s, topic_pop), reverse=True,
            )
            free_rooms = [r for r in available if r.room_id not in used_rooms]
            for idx, sess in enumerate(unassigned):
                if idx < len(free_rooms):
                    sess.room = free_rooms[idx]
                    used_rooms.add(free_rooms[idx].room_id)

            # Update continuity map
            for sess in sessions:
                if sess.topic and sess.room:
                    prev_topic_room[sess.topic.topic_id] = sess.room

    program.metadata["generated"] = "rooms_assigned"
    return program
