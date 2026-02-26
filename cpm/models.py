"""Core data models for Conference Program Manager."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConstraintOp(str, Enum):
    """Supported constraint operators."""
    EQ = "="        # paper_id = day_3
    IN = "in"       # room_name in {day_4, day_5}
    NEQ = "!="      # paper_id != day_1
    NOT_IN = "not_in"
    LT = "<"        # paper_1 < paper_2  (precedence)


class SlotKind(str, Enum):
    """Kind of time-slot in the programme."""
    SESSION = "session"
    BREAK = "break"
    LUNCH = "lunch"
    DINNER = "dinner"
    PLENARY = "plenary"
    ROOM_CHANGE = "room_change"


# ---------------------------------------------------------------------------
# Small value objects
# ---------------------------------------------------------------------------

@dataclass
class Author:
    name: str
    affiliation: str = ""
    department: str = ""
    email: str = ""


@dataclass
class Topic:
    topic_id: int
    name: str


@dataclass
class Room:
    room_id: int
    name: str
    capacity: int = 0


@dataclass
class Chair:
    chair_id: int
    name: str
    email: str = ""
    arrival_day: int = 1      # first day they are present
    departure_day: int = 999  # last day they are present
    topic_ids: list[int] = field(default_factory=list)  # inferred from papers


@dataclass
class Paper:
    paper_id: int
    title: str
    authors: list[Author] = field(default_factory=list)
    corr_email: str = ""
    pref_ids: list[int] = field(default_factory=list)
    comment: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

@dataclass
class Constraint:
    """A single scheduling constraint.

    Examples (text form):
        paper_437 = day_3
        section_S1 = "Welcome"
        room_Pinus in {day_4, day_5}
    """
    cid: str = ""                # unique constraint id
    subject_type: str = ""       # paper, section, room, chair, topic ...
    subject_id: str = ""         # identifier of the subject
    op: ConstraintOp = ConstraintOp.EQ
    value: list[str] = field(default_factory=list)  # target value(s)
    description: str = ""

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    _PATTERN = re.compile(
        r"^\s*(?P<subj>\w+)"
        r"\s+(?P<op>=|!=|<|in|not_in)\s+"
        r"(?P<val>.+?)\s*$",
        re.IGNORECASE,
    )

    @classmethod
    def from_text(cls, text: str, cid: str = "") -> "Constraint":
        """Parse ``subject op value`` text into a Constraint."""
        m = cls._PATTERN.match(text)
        if not m:
            raise ValueError(f"Cannot parse constraint: {text!r}")
        raw_subj = m.group("subj")
        op_str = m.group("op").lower()
        raw_val = m.group("val").strip()

        # Split subject into type + id  (e.g. paper_437 -> paper, 437)
        parts = raw_subj.split("_", 1)
        subj_type = parts[0]
        subj_id = parts[1] if len(parts) > 1 else ""

        op = ConstraintOp(op_str)

        # Parse value: could be {a, b, c} set or "string" or bare token
        if raw_val.startswith("{") and raw_val.endswith("}"):
            values = [v.strip().strip('"').strip("'") for v in raw_val[1:-1].split(",")]
        else:
            values = [raw_val.strip('"').strip("'")]

        return cls(
            cid=cid,
            subject_type=subj_type,
            subject_id=subj_id,
            op=op,
            value=values,
        )

    def to_text(self) -> str:
        if len(self.value) > 1:
            val_str = "{" + ", ".join(self.value) + "}"
        else:
            val_str = self.value[0] if self.value else ""
        subj = f"{self.subject_type}_{self.subject_id}" if self.subject_id else self.subject_type
        return f"{subj} {self.op.value} {val_str}"


# ---------------------------------------------------------------------------
# Time-related
# ---------------------------------------------------------------------------

@dataclass
class TimeSlot:
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    kind: SlotKind = SlotKind.SESSION
    label: str = ""
    day: int = 1

    @property
    def start_time(self) -> time:
        h, m = map(int, self.start.split(":"))
        return time(h, m)

    @property
    def end_time(self) -> time:
        h, m = map(int, self.end.split(":"))
        return time(h, m)

    @property
    def duration_minutes(self) -> int:
        s = self.start_time
        e = self.end_time
        return (e.hour * 60 + e.minute) - (s.hour * 60 + s.minute)


# ---------------------------------------------------------------------------
# Session & Program
# ---------------------------------------------------------------------------

@dataclass
class Session:
    session_id: str
    day: int = 1
    time_slot: Optional[TimeSlot] = None
    topic: Optional[Topic] = None
    room: Optional[Room] = None
    chair: Optional[Chair] = None
    papers: list[Paper] = field(default_factory=list)
    label: str = ""
    is_fixed: bool = False

    @property
    def capacity(self) -> int:
        if self.time_slot is None:
            return 0
        from .config import ScheduleConfig  # avoid circular
        # fallback: derive from presentation duration
        return 0


@dataclass
class DayProgram:
    day: int
    slots: list[dict] = field(default_factory=list)
    # Each slot: {"time_slot": TimeSlot-dict, "sessions": [Session-dict]}


@dataclass
class Program:
    """Full conference programme."""
    days: list[DayProgram] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return _to_dict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Program":
        return _program_from_dict(d)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "Program":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Column-mapping configuration for data-prep
# ---------------------------------------------------------------------------

@dataclass
class ColumnMapping:
    """Describes how columns in the paper CSV map to Paper fields.

    Each field is either:
      - a single column name  (str)
      - a list of column names (list[str])
      - a glob/pattern string  (str containing * or ##)
    """
    paper_id: str = "paper_id"
    title: str = "title"
    author_names: str | list[str] = "f_name"
    author_affiliations: str | list[str] = "f_affiliation"
    author_departments: str | list[str] = ""
    author_emails: str | list[str] = "f_email"
    corr_email: str = "corr_email"
    pref_columns: str | list[str] = "pref_one"
    comment: str = "comments"
    separator: str = ";"
    encoding: str = "utf-8"

    def resolve_columns(self, all_columns: list[str]) -> dict[str, list[str]]:
        """Expand patterns (``*_mail``, ``author_##``) against *all_columns*."""
        result: dict[str, list[str]] = {}
        for attr in (
            "author_names", "author_affiliations", "author_departments",
            "author_emails", "pref_columns",
        ):
            spec = getattr(self, attr)
            result[attr] = _resolve_spec(spec, all_columns)
        return result


def _resolve_spec(spec: str | list[str], columns: list[str]) -> list[str]:
    """Return concrete column names from a spec (list, pattern, or scalar)."""
    if isinstance(spec, list):
        return spec
    if not spec:
        return []
    # Pattern detection
    if "*" in spec or "##" in spec:
        regex = spec.replace("##", r"\d{1,2}").replace("*", r".*")
        pat = re.compile(f"^{regex}$", re.IGNORECASE)
        return [c for c in columns if pat.match(c)]
    return [spec]


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclass instances to dicts."""
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _program_from_dict(d: dict) -> Program:
    """Reconstruct a Program from a dict (loaded from JSON)."""
    days: list[DayProgram] = []
    for dd in d.get("days", []):
        slots = []
        for s in dd.get("slots", []):
            ts_raw = s.get("time_slot", {})
            ts = TimeSlot(
                start=ts_raw.get("start", ""),
                end=ts_raw.get("end", ""),
                kind=SlotKind(ts_raw.get("kind", "session")),
                label=ts_raw.get("label", ""),
                day=ts_raw.get("day", dd.get("day", 1)),
            )
            sessions: list[dict] = []
            for sess_raw in s.get("sessions", []):
                sess = _session_from_dict(sess_raw)
                sessions.append(sess)
            slots.append({"time_slot": ts, "sessions": sessions})
        days.append(DayProgram(day=dd.get("day", 1), slots=slots))
    return Program(days=days, metadata=d.get("metadata", {}))


def _session_from_dict(d: dict) -> Session:
    ts_raw = d.get("time_slot")
    ts = None
    if ts_raw:
        ts = TimeSlot(
            start=ts_raw.get("start", ""),
            end=ts_raw.get("end", ""),
            kind=SlotKind(ts_raw.get("kind", "session")),
            label=ts_raw.get("label", ""),
            day=ts_raw.get("day", 1),
        )
    topic_raw = d.get("topic")
    topic = Topic(**topic_raw) if topic_raw else None
    room_raw = d.get("room")
    room = Room(**room_raw) if room_raw else None
    chair_raw = d.get("chair")
    if chair_raw:
        _chair_fields = {f for f in Chair.__dataclass_fields__}
        chair = Chair(**{k: v for k, v in chair_raw.items() if k in _chair_fields})
    else:
        chair = None
    papers = []
    for p in d.get("papers", []):
        authors = [Author(**a) for a in p.get("authors", [])]
        papers.append(Paper(
            paper_id=p["paper_id"],
            title=p.get("title", ""),
            authors=authors,
            corr_email=p.get("corr_email", ""),
            pref_ids=p.get("pref_ids", []),
            comment=p.get("comment", ""),
            extra=p.get("extra", {}),
        ))
    return Session(
        session_id=d.get("session_id", ""),
        day=d.get("day", 1),
        time_slot=ts,
        topic=topic,
        room=room,
        chair=chair,
        papers=papers,
        label=d.get("label", ""),
        is_fixed=d.get("is_fixed", False),
    )
