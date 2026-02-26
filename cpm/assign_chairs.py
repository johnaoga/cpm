"""Assign chairs to sessions in an existing programme.

Strategy:
  - A chair is only assigned on days they are present (arrival ≤ day ≤ departure).
  - A chair must NOT chair a session in which they have a paper.
  - A chair must NOT chair a session in a time-slot where they present a paper
    in another parallel session (they might be the presenter).
  - Prefer assigning a chair to a session whose topic matches one of their
    topics (inferred from their own papers).
  - Distribute chairs as evenly as possible across sessions.
  - A chair should not be assigned to two sessions in the same time-slot.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from .config import ScheduleConfig
from .models import (
    Chair,
    Paper,
    Program,
    Session,
    SlotKind,
)

logger = logging.getLogger(__name__)


def _infer_chair_topics(
    chairs: list[Chair],
    papers: list[Paper],
) -> None:
    """Populate ``chair.topic_ids`` by matching chair email / name to paper
    authors.  Modifies chairs in-place."""
    # Build lookup: lowercase email → paper pref_ids
    email_prefs: dict[str, list[int]] = defaultdict(list)
    name_prefs: dict[str, list[int]] = defaultdict(list)
    for p in papers:
        for a in p.authors:
            if a.email:
                email_prefs[a.email.lower()].extend(p.pref_ids)
            if a.name:
                name_prefs[a.name.lower()].extend(p.pref_ids)

    for ch in chairs:
        if ch.topic_ids:
            continue  # already set
        prefs: list[int] = []
        if ch.email:
            prefs.extend(email_prefs.get(ch.email.lower(), []))
        if ch.name:
            prefs.extend(name_prefs.get(ch.name.lower(), []))
        ch.topic_ids = list(dict.fromkeys(prefs))  # deduplicate, keep order


def _presenting_paper_ids_in_session(sess: Session) -> set[int]:
    """Return paper IDs in *sess*."""
    return {p.paper_id for p in sess.papers}


def _presenting_authors_in_session(sess: Session) -> set[str]:
    """Return lowercase emails of all authors in *sess*."""
    emails: set[str] = set()
    for p in sess.papers:
        for a in p.authors:
            if a.email:
                emails.add(a.email.lower())
    return emails


def _chair_presents_in_session(chair: Chair, sess: Session) -> bool:
    """True if the chair is an author of any paper in *sess*."""
    if chair.email:
        return chair.email.lower() in _presenting_authors_in_session(sess)
    return False


def _chair_presents_in_slot(chair: Chair, slot_sessions: list[Session]) -> bool:
    """True if the chair presents in *any* session of this parallel slot."""
    for sess in slot_sessions:
        if _chair_presents_in_session(chair, sess):
            return True
    return False


def assign_chairs(
    program: Program,
    chairs: list[Chair],
    cfg: ScheduleConfig,
    papers: Optional[list[Paper]] = None,
) -> Program:
    """Assign chairs to sessions. Modifies *program* in-place."""
    if not chairs:
        logger.warning("No chairs provided; skipping chair assignment.")
        return program

    # Infer chair topics from papers (if available)
    if papers:
        _infer_chair_topics(chairs, papers)

    # Collect all (day, slot_sessions) groups
    slot_groups: list[tuple[int, list[Session]]] = []
    for day_prog in program.days:
        for slot in day_prog.slots:
            ts = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue
            slot_groups.append((day_prog.day, slot["sessions"]))

    # Track load for even distribution
    chair_load: dict[int, int] = defaultdict(int)

    for day, sessions in slot_groups:
        used_in_slot: set[int] = set()

        for sess in sessions:
            # Score each candidate chair
            best_chair: Optional[Chair] = None
            best_score = -float("inf")

            for ch in chairs:
                # Hard constraints
                if ch.chair_id in used_in_slot:
                    continue
                if day < ch.arrival_day or day > ch.departure_day:
                    continue
                if _chair_presents_in_session(ch, sess):
                    continue
                if _chair_presents_in_slot(ch, sessions):
                    continue

                # Soft score: topic match + load balancing
                score = 0.0
                # Topic affinity: bonus if chair's topic matches session topic
                if sess.topic and ch.topic_ids:
                    if sess.topic.topic_id in ch.topic_ids:
                        score += 100
                # Prefer less-loaded chairs
                score -= chair_load[ch.chair_id] * 10

                if score > best_score:
                    best_score = score
                    best_chair = ch

            if best_chair:
                sess.chair = best_chair
                used_in_slot.add(best_chair.chair_id)
                chair_load[best_chair.chair_id] += 1
            else:
                logger.warning(
                    "No eligible chair for session %s (day %d)",
                    sess.session_id, day,
                )

    program.metadata["generated"] = "chairs_assigned"
    return program
