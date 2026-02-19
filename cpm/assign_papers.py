"""Assign papers to sessions using OR-Tools CP-SAT solver.

The assignment uses a two-phase approach:
  Phase 1: Assign topics to sessions (greedy, based on paper-count per topic).
  Phase 2: Assign papers to sessions via CP-SAT, using topic affinity as
           the objective and respecting capacity + constraints.

This avoids the combinatorial explosion of jointly optimising topic + paper
assignment (O(papers × sessions × topics) auxiliary variables).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import numpy as np
from ortools.sat.python import cp_model

from .config import ScheduleConfig
from .models import (
    Constraint,
    ConstraintOp,
    DayProgram,
    Paper,
    Program,
    Session,
    SlotKind,
    Topic,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Capacity pre-flight check
# ---------------------------------------------------------------------------

@dataclass
class CapacityReport:
    """Result of a pre-flight capacity check."""
    n_papers: int
    n_sessions: int
    total_capacity: int
    deficit: int  # >0 means not enough capacity
    suggestions: list[str]

    @property
    def feasible(self) -> bool:
        return self.deficit <= 0

    def summary(self) -> str:
        lines = [
            f"Papers to assign : {self.n_papers}",
            f"Available sessions : {self.n_sessions}",
            f"Total capacity     : {self.total_capacity} papers",
        ]
        if self.feasible:
            lines.append(f"Status             : OK (surplus of {-self.deficit} slots)")
        else:
            lines.append(f"Status             : INSUFFICIENT (deficit of {self.deficit} papers)")
            lines.append("")
            lines.append("Suggestions to resolve:")
            for i, s in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {s}")
        return "\n".join(lines)


def check_capacity(
    program: Program,
    n_papers: int,
    cfg: ScheduleConfig,
) -> CapacityReport:
    """Check whether the programme has enough session capacity for *n_papers*.

    Returns a CapacityReport with diagnostics and suggestions.
    """
    sessions = _collect_sessions(program)
    caps = [_session_capacity(s, cfg) for s in sessions]
    usable = [(j, c) for j, c in enumerate(caps) if not sessions[j].is_fixed]
    total_cap = sum(c for _, c in usable)
    n_sessions = len(usable)
    deficit = n_papers - total_cap

    suggestions: list[str] = []
    if deficit > 0:
        # How many extra sessions would be needed at current presentation duration
        pps = cfg.papers_per_session or 1
        extra_sessions = (deficit + pps - 1) // pps
        extra_rooms = (extra_sessions + cfg.num_days - 1) // cfg.num_days

        suggestions.append(
            f"Increase num_available_rooms / max_rooms_per_day "
            f"(adding ~{extra_rooms} rooms would cover the deficit)"
        )
        suggestions.append(
            "Increase num_days in the schedule config"
        )
        suggestions.append(
            f"Reduce presentation_duration_min "
            f"(currently {cfg.presentation_duration_min} min; "
            f"e.g. {max(5, cfg.presentation_duration_min - 5)} min "
            f"would give ~{total_cap * cfg.presentation_duration_min // max(5, cfg.presentation_duration_min - 5)} capacity)"
        )
        suggestions.append(
            "Extend day_start / day_end to add more session time"
        )
        suggestions.append(
            "Remove or shorten breaks (morning_break, afternoon_break, lunch)"
        )

    return CapacityReport(
        n_papers=n_papers,
        n_sessions=n_sessions,
        total_capacity=total_cap,
        deficit=deficit,
        suggestions=suggestions,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_capacity(session: Session, cfg: ScheduleConfig) -> int:
    """How many papers fit into this session."""
    if session.time_slot is None:
        return 0
    dur = session.time_slot.duration_minutes
    return dur // cfg.presentation_duration_min


def _collect_sessions(program: Program) -> list[Session]:
    """Flatten all SESSION-type slots into a list of Session objects."""
    sessions: list[Session] = []
    for day_prog in program.days:
        for slot in day_prog.slots:
            ts = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue
            for sess in slot["sessions"]:
                if isinstance(sess, dict):
                    continue
                sessions.append(sess)
    return sessions


def _build_topic_groups(
    papers: list[Paper],
    topics: list[Topic],
    topic_sim_matrix: Optional[np.ndarray] = None,
    merge_threshold: float = 0.75,
    min_group_size: int = 3,
) -> dict[int, list[int]]:
    """Group topic IDs so that small/similar topics are merged.

    Returns {canonical_topic_id: [member_topic_ids]}.
    """
    tid_list = [t.topic_id for t in topics]
    groups: dict[int, list[int]] = {tid: [tid] for tid in tid_list}

    if topic_sim_matrix is None:
        return groups

    pref_count: dict[int, int] = defaultdict(int)
    for p in papers:
        if p.pref_ids:
            pref_count[p.pref_ids[0]] += 1

    merged_into: dict[int, int] = {}

    for i, tid_i in enumerate(tid_list):
        if tid_i in merged_into:
            continue
        for j in range(i + 1, len(tid_list)):
            tid_j = tid_list[j]
            if tid_j in merged_into:
                continue
            sim = float(topic_sim_matrix[i, j])
            if sim < merge_threshold:
                continue
            cnt_i = pref_count.get(tid_i, 0)
            cnt_j = pref_count.get(tid_j, 0)
            if cnt_i <= min_group_size or cnt_j <= min_group_size:
                canonical = tid_i
                groups[canonical].append(tid_j)
                merged_into[tid_j] = canonical
                if tid_j in groups:
                    groups[canonical].extend(
                        [x for x in groups.pop(tid_j) if x != tid_j]
                    )
                logger.info(
                    "Merging topic %d into %d (sim=%.3f, counts=%d/%d)",
                    tid_j, canonical, sim, cnt_j, cnt_i,
                )

    return groups


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _paper_topic_score(
    paper: Paper,
    topic_id: int,
    topic_groups: dict[int, list[int]],
    sbert_scores: Optional[dict[int, dict[int, float]]] = None,
) -> int:
    """Integer score (higher = better) for placing *paper* in a session
    with canonical topic *topic_id*."""
    member_tids = topic_groups.get(topic_id, [topic_id])

    if sbert_scores and paper.paper_id in sbert_scores:
        pscores = sbert_scores[paper.paper_id]
        best = max((pscores.get(tid, 0.0) for tid in member_tids), default=0.0)
        return int(best * 100)

    for rank, weight in enumerate([100, 60]):
        if rank < len(paper.pref_ids):
            if paper.pref_ids[rank] in member_tids:
                return weight
    return 1  # small baseline so every paper can go somewhere


# ---------------------------------------------------------------------------
# Constraint extraction
# ---------------------------------------------------------------------------

def _parse_constraints(
    constraints: list[Constraint],
    papers: list[Paper],
    sessions: list[Session],
) -> dict:
    """Extract solver-relevant constraints into lookup dicts."""
    paper_day: dict[int, list[int]] = {}
    paper_session: dict[int, list[str]] = {}
    paper_not_day: dict[int, list[int]] = {}
    session_labels: dict[str, str] = {}

    for c in constraints:
        if c.subject_type == "paper":
            pid = int(c.subject_id) if c.subject_id.isdigit() else 0
            if not pid:
                continue
            days = []
            sess_ids = []
            for v in c.value:
                if v.startswith("day_"):
                    try:
                        days.append(int(v.split("_")[1]))
                    except (IndexError, ValueError):
                        pass
                elif v.startswith("S"):
                    sess_ids.append(v)
            if c.op in (ConstraintOp.EQ, ConstraintOp.IN):
                if days:
                    paper_day[pid] = days
                if sess_ids:
                    paper_session[pid] = sess_ids
            elif c.op in (ConstraintOp.NEQ, ConstraintOp.NOT_IN):
                if days:
                    paper_not_day.setdefault(pid, []).extend(days)

        elif c.subject_type == "section":
            if c.op == ConstraintOp.EQ and c.value:
                session_labels[c.subject_id] = c.value[0]

    return {
        "paper_day": paper_day,
        "paper_session": paper_session,
        "paper_not_day": paper_not_day,
        "session_labels": session_labels,
    }


# ---------------------------------------------------------------------------
# Phase 1: Topic → Session assignment (greedy)
# ---------------------------------------------------------------------------

def _assign_topics_to_sessions(
    sessions: list[Session],
    papers: list[Paper],
    topics: list[Topic],
    topic_groups: dict[int, list[int]],
    caps: list[int],
    sbert_scores: Optional[dict[int, dict[int, float]]] = None,
) -> dict[int, int]:
    """Greedily assign a canonical topic to each non-fixed session.

    Returns {session_index: canonical_topic_id}.
    """
    # Count papers per canonical topic (using primary pref)
    topic_paper_count: dict[int, int] = defaultdict(int)
    for p in papers:
        if not p.pref_ids:
            continue
        for ctid, members in topic_groups.items():
            if p.pref_ids[0] in members:
                topic_paper_count[ctid] += 1
                break

    # Sort canonical topics by paper count descending
    sorted_topics = sorted(topic_paper_count.items(), key=lambda x: -x[1])

    sess_topic: dict[int, int] = {}
    used_sessions: set[int] = set()

    # Skip fixed sessions
    for j, sess in enumerate(sessions):
        if sess.is_fixed:
            used_sessions.add(j)

    # Assign topics round-robin: largest topic first, fill sessions
    for ctid, count in sorted_topics:
        if count == 0:
            continue
        remaining = count
        while remaining > 0:
            # Find best available session (prefer larger capacity)
            best_j = -1
            best_cap = 0
            for j in range(len(sessions)):
                if j in used_sessions:
                    continue
                if caps[j] > best_cap:
                    best_cap = caps[j]
                    best_j = j
            if best_j < 0:
                logger.warning(
                    "No more sessions available for topic %d (%d papers remaining)",
                    ctid, remaining,
                )
                break
            sess_topic[best_j] = ctid
            used_sessions.add(best_j)
            remaining -= best_cap

    # Assign remaining unused sessions a topic (the one with most overflow)
    overflow = {
        ctid: topic_paper_count.get(ctid, 0) - sum(
            caps[j] for j, t in sess_topic.items() if t == ctid
        )
        for ctid in topic_paper_count
    }
    for j in range(len(sessions)):
        if j in used_sessions:
            continue
        # Pick topic with largest overflow
        if overflow:
            best_tid = max(overflow, key=lambda t: overflow[t])
            sess_topic[j] = best_tid
            overflow[best_tid] -= caps[j]
            used_sessions.add(j)

    return sess_topic


# ---------------------------------------------------------------------------
# Phase 2: Paper → Session assignment (CP-SAT)
# ---------------------------------------------------------------------------

def assign_papers(
    program: Program,
    papers: list[Paper],
    topics: list[Topic],
    cfg: ScheduleConfig,
    sbert_scores: Optional[dict[int, dict[int, float]]] = None,
    topic_sim_matrix: Optional[np.ndarray] = None,
    merge_threshold: float = 0.75,
    min_group_size: int = 3,
) -> Program:
    """Assign papers to sessions in *program*.

    Phase 1: greedy topic→session assignment.
    Phase 2: CP-SAT paper→session assignment maximising topic affinity.

    Returns the modified Program.
    """
    sessions = _collect_sessions(program)
    if not sessions:
        raise ValueError("No sessions found in the programme.")

    topic_groups = _build_topic_groups(
        papers, topics, topic_sim_matrix, merge_threshold, min_group_size,
    )
    tid_to_topic = {t.topic_id: t for t in topics}

    parsed = _parse_constraints(cfg.constraints, papers, sessions)

    caps = [_session_capacity(s, cfg) for s in sessions]
    total_cap = sum(c for j, c in enumerate(caps) if not sessions[j].is_fixed)
    n_papers = len(papers)
    n_sessions = len(sessions)

    logger.info(
        "Assigning %d papers to %d sessions (total capacity %d)",
        n_papers, n_sessions, total_cap,
    )

    # ── Phase 1: topic → session ──
    sess_topic_map = _assign_topics_to_sessions(
        sessions, papers, topics, topic_groups, caps, sbert_scores,
    )

    for j, ctid in sess_topic_map.items():
        if ctid in tid_to_topic:
            sessions[j].topic = tid_to_topic[ctid]

    topic_summary = defaultdict(int)
    for ctid in sess_topic_map.values():
        topic_summary[ctid] += 1
    logger.info("Topic assignment: %s", dict(topic_summary))

    # ── Phase 2: paper → session (CP-SAT) ──
    paper_idx = {p.paper_id: i for i, p in enumerate(papers)}

    model = cp_model.CpModel()

    # x[i][j] = 1 iff paper i assigned to session j
    x = [
        [model.new_bool_var(f"x_{i}_{j}") for j in range(n_sessions)]
        for i in range(n_papers)
    ]

    # Each paper assigned to at most one session (exactly one if capacity allows)
    for i in range(n_papers):
        model.add(sum(x[i][j] for j in range(n_sessions)) <= 1)

    # Session capacity
    for j in range(n_sessions):
        model.add(sum(x[i][j] for i in range(n_papers)) <= caps[j])

    # Fixed sessions: no papers
    for j, sess in enumerate(sessions):
        if sess.is_fixed:
            for i in range(n_papers):
                model.add(x[i][j] == 0)

    # Hard constraints from config
    for pid, allowed_days in parsed["paper_day"].items():
        if pid not in paper_idx:
            continue
        i = paper_idx[pid]
        for j, sess in enumerate(sessions):
            if sess.day not in allowed_days:
                model.add(x[i][j] == 0)

    for pid, not_days in parsed["paper_not_day"].items():
        if pid not in paper_idx:
            continue
        i = paper_idx[pid]
        for j, sess in enumerate(sessions):
            if sess.day in not_days:
                model.add(x[i][j] == 0)

    for pid, allowed_sids in parsed["paper_session"].items():
        if pid not in paper_idx:
            continue
        i = paper_idx[pid]
        for j, sess in enumerate(sessions):
            if sess.session_id not in allowed_sids:
                model.add(x[i][j] == 0)

    # Objective: maximise paper-topic affinity + bonus for assigning papers
    ASSIGN_BONUS = 200  # strong incentive to assign every paper
    obj_terms = []

    for i, paper in enumerate(papers):
        # Bonus for being assigned at all
        assigned_i = model.new_bool_var(f"a_{i}")
        model.add_max_equality(assigned_i, [x[i][j] for j in range(n_sessions)])
        obj_terms.append(ASSIGN_BONUS * assigned_i)

        for j in range(n_sessions):
            if sessions[j].is_fixed:
                continue
            ctid = sess_topic_map.get(j)
            if ctid is None:
                continue
            score = _paper_topic_score(
                paper, ctid, topic_groups, sbert_scores,
            )
            if score > 0:
                obj_terms.append(score * x[i][j])

    model.maximize(sum(obj_terms))

    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 120
    solver.parameters.num_workers = 8
    status = solver.solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT solver failed with status {status}")

    assigned_count = 0
    for i in range(n_papers):
        for j in range(n_sessions):
            if solver.value(x[i][j]):
                sessions[j].papers.append(papers[i])
                assigned_count += 1
                break

    logger.info(
        "Phase 2 done: status=%s, objective=%.1f, %d/%d papers assigned",
        solver.status_name(status),
        solver.objective_value,
        assigned_count,
        n_papers,
    )

    program.metadata["generated"] = "papers_assigned"
    program.metadata["solver_objective"] = solver.objective_value
    program.metadata["papers_assigned"] = assigned_count
    program.metadata["papers_total"] = n_papers
    return program
