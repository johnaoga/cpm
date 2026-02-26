"""Schedule configuration loading / saving (JSON-based)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .models import Constraint


@dataclass
class PlenarySlot:
    """A reserved slot in the schedule (e.g. keynote, welcome, closing)."""
    label: str
    day: int
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    room: str = ""  # optional: pin to a specific room


@dataclass
class ScheduleConfig:
    """All tunables for building a conference programme."""

    # --- conference shape ---
    num_days: int = 3
    max_session_duration_min: int = 90
    presentation_duration_min: int = 20
    num_available_rooms: int = 5
    max_rooms_per_day: int = 5

    # --- daily times ---
    day_start: str = "09:00"        # default day start
    day_end: str = "17:30"          # default day end
    first_day_start: str = ""       # override for day-1 (empty => use day_start)
    last_day_end: str = ""          # override for last day

    # --- breaks ---
    break_duration_min: int = 30
    morning_break: bool = True
    afternoon_break: bool = True
    lunch_included: bool = True
    lunch_duration_min: int = 60
    dinner_included: bool = False
    dinner_start: str = "19:00"

    # --- break/lunch target placement times ("HH:MM", empty = auto) ---
    morning_break_target: str = "10:30"
    lunch_target: str = "12:00"
    afternoon_break_target: str = "15:00"

    # --- room-change penalty ---
    room_change_penalty_min: int = 5

    # --- plenary / reserved slots ---
    plenary_slots: list[PlenarySlot] = field(default_factory=list)

    # --- constraints (free-form list) ---
    constraints: list[Constraint] = field(default_factory=list)

    # --- extra (catch-all for future tunables) ---
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def papers_per_session(self) -> int:
        return self.max_session_duration_min // self.presentation_duration_min

    def effective_day_start(self, day: int) -> str:
        if day == 1 and self.first_day_start:
            return self.first_day_start
        return self.day_start

    def effective_day_end(self, day: int) -> str:
        if day == self.num_days and self.last_day_end:
            return self.last_day_end
        return self.day_end

    # ------------------------------------------------------------------
    # IO
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self._to_dict(), indent=2, ensure_ascii=False)
        )

    @classmethod
    def load(cls, path: str | Path) -> "ScheduleConfig":
        raw = json.loads(Path(path).read_text())
        return cls._from_dict(raw)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def _to_dict(self) -> dict:
        d: dict[str, Any] = {}
        for k, v in self.__dict__.items():
            if k == "plenary_slots":
                d[k] = [ps.__dict__ for ps in v]
            elif k == "constraints":
                d[k] = [c.to_text() for c in v]
            else:
                d[k] = v
        return d

    @classmethod
    def _from_dict(cls, raw: dict) -> "ScheduleConfig":
        prelim_raw = raw.pop("plenary_slots", [])
        constr_raw = raw.pop("constraints", [])
        extra = raw.pop("extra", {})

        # Filter raw to only valid fields
        valid = {f for f in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in raw.items() if k in valid}

        cfg = cls(**kwargs, extra=extra)

        cfg.plenary_slots = [
            PlenarySlot(**ps) if isinstance(ps, dict) else ps
            for ps in prelim_raw
        ]
        cfg.constraints = []
        for i, c in enumerate(constr_raw):
            if isinstance(c, str):
                cfg.constraints.append(Constraint.from_text(c, cid=f"C{i+1:03d}"))
            elif isinstance(c, dict):
                cfg.constraints.append(Constraint(**c))
        return cfg

    # ------------------------------------------------------------------
    # Constraint management helpers
    # ------------------------------------------------------------------

    def add_constraint(self, text: str) -> Constraint:
        cid = f"C{len(self.constraints)+1:03d}"
        c = Constraint.from_text(text, cid=cid)
        self.constraints.append(c)
        return c

    def remove_constraint(self, cid: str) -> bool:
        before = len(self.constraints)
        self.constraints = [c for c in self.constraints if c.cid != cid]
        return len(self.constraints) < before

    def edit_constraint(self, cid: str, new_text: str) -> Optional[Constraint]:
        for i, c in enumerate(self.constraints):
            if c.cid == cid:
                new_c = Constraint.from_text(new_text, cid=cid)
                self.constraints[i] = new_c
                return new_c
        return None

    def list_constraints(self) -> list[Constraint]:
        return list(self.constraints)
