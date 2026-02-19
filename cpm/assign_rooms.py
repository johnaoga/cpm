"""Assign rooms to sessions in an existing programme.

Strategy:
  - Sessions in the same time-slot get distinct rooms.
  - Prefer keeping the same topic in the same room across consecutive slots
    (minimise room-change penalty).
  - Respect room constraints from the config (e.g. room only on certain days).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from .config import ScheduleConfig
from .models import (
    ConstraintOp,
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


def assign_rooms(
    program: Program,
    rooms: list[Room],
    cfg: ScheduleConfig,
) -> Program:
    """Assign rooms to every session slot in *program*.

    Modifies the programme in-place and returns it.
    """
    room_day_constraints = _parse_room_constraints(cfg)

    # For each day, track topic→room assignment for continuity
    prev_topic_room: dict[int, Room] = {}

    for day_prog in program.days:
        day = day_prog.day
        available = [
            r for r in rooms
            if r.name not in room_day_constraints
            or day in room_day_constraints[r.name]
        ]
        if not available:
            available = list(rooms)

        for slot in day_prog.slots:
            ts = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue

            sessions: list[Session] = slot["sessions"]
            used_rooms: set[int] = set()

            # First pass: assign rooms to sessions whose topic already had a room
            for sess in sessions:
                if sess.topic and sess.topic.topic_id in prev_topic_room:
                    candidate = prev_topic_room[sess.topic.topic_id]
                    if candidate.room_id not in used_rooms and candidate in available:
                        sess.room = candidate
                        used_rooms.add(candidate.room_id)

            # Second pass: fill remaining sessions
            free_rooms = [r for r in available if r.room_id not in used_rooms]
            free_idx = 0
            for sess in sessions:
                if sess.room is not None:
                    continue
                if free_idx < len(free_rooms):
                    sess.room = free_rooms[free_idx]
                    used_rooms.add(free_rooms[free_idx].room_id)
                    free_idx += 1

            # Update continuity map
            for sess in sessions:
                if sess.topic and sess.room:
                    prev_topic_room[sess.topic.topic_id] = sess.room

    program.metadata["generated"] = "rooms_assigned"
    return program
