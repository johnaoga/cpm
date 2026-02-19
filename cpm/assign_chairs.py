"""Assign chairs to sessions in an existing programme.

Strategy:
  - Distribute chairs as evenly as possible across sessions.
  - A chair should not be assigned to two sessions in the same time-slot.
  - Prefer assigning a chair to sessions on a single day to reduce travel.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from .config import ScheduleConfig
from .models import (
    Chair,
    Program,
    Session,
    SlotKind,
)

logger = logging.getLogger(__name__)


def assign_chairs(
    program: Program,
    chairs: list[Chair],
    cfg: ScheduleConfig,
) -> Program:
    """Assign chairs to sessions. Modifies *program* in-place."""
    if not chairs:
        logger.warning("No chairs provided; skipping chair assignment.")
        return program

    # Collect all session-slot groups (sessions that run in parallel)
    slot_groups: list[list[Session]] = []
    for day_prog in program.days:
        for slot in day_prog.slots:
            ts = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue
            slot_groups.append(slot["sessions"])

    # Round-robin assignment ensuring no chair is in two parallel sessions
    chair_load: dict[int, int] = defaultdict(int)  # chair_id -> count
    chair_idx = 0

    for group in slot_groups:
        used_in_slot: set[int] = set()
        for sess in group:
            # Find next chair not yet used in this parallel slot
            attempts = 0
            while attempts < len(chairs):
                c = chairs[chair_idx % len(chairs)]
                if c.chair_id not in used_in_slot:
                    sess.chair = c
                    used_in_slot.add(c.chair_id)
                    chair_load[c.chair_id] += 1
                    chair_idx += 1
                    break
                chair_idx += 1
                attempts += 1

    program.metadata["generated"] = "chairs_assigned"
    return program
