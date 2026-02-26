"""Data preparation: load paper CSV, topics, rooms, chairs with column mapping."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .models import Author, Chair, ColumnMapping, Paper, Room, Topic

logger = logging.getLogger(__name__)


def _fix_mojibake(text: str) -> str:
    """Repair mojibake caused by mixed encoding (UTF-8 bytes in a latin-1 file).

    Tries to re-encode the string back to bytes (via cp1252 then latin-1) and
    decode as UTF-8.  This handles files where some entries were pasted as
    UTF-8 while the rest is latin-1 / cp1252.
    """
    if not text or all(ord(c) < 128 for c in text):
        return text
    # Try whole-string repair: cp1252 first (handles \x80-\x9F → Unicode),
    # then latin-1 as fallback.
    for enc in ("cp1252", "latin-1"):
        try:
            return text.encode(enc).decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    # Per-character repair: split into runs of encodable chars, attempt
    # re-decode of each run that contains non-ASCII.
    result: list[str] = []
    buf: list[str] = []

    def _flush() -> None:
        if not buf:
            return
        chunk = "".join(buf)
        buf.clear()
        if all(ord(c) < 128 for c in chunk):
            result.append(chunk)
            return
        for enc in ("cp1252", "latin-1"):
            try:
                result.append(chunk.encode(enc).decode("utf-8"))
                return
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue
        result.append(chunk)

    for ch in text:
        try:
            ch.encode("cp1252")
            buf.append(ch)
        except UnicodeEncodeError:
            _flush()
            result.append(ch)

    _flush()
    return "".join(result)


def _detect_encoding(path: str | Path, configured: str = "utf-8") -> str:
    """Try UTF-8 first, then *configured*, then latin-1.

    Returns the first encoding that reads the file without error.
    This prevents mojibake when the configured encoding is wrong.
    """
    raw = Path(path).read_bytes()
    # Strip BOM if present
    if raw[:3] == b'\xef\xbb\xbf':
        return "utf-8-sig"
    for enc in dict.fromkeys(["utf-8", configured, "latin-1"]):
        try:
            raw.decode(enc)
            if enc != configured:
                logger.info(
                    "Encoding auto-detected as %s (configured: %s) for %s",
                    enc, configured, path,
                )
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return configured  # last resort


# ---------------------------------------------------------------------------
# Column-mapping config IO
# ---------------------------------------------------------------------------

def save_column_mapping(mapping: ColumnMapping, path: str | Path) -> None:
    """Persist a ColumnMapping to JSON."""
    d = mapping.__dict__.copy()
    Path(path).write_text(json.dumps(d, indent=2, ensure_ascii=False))


def load_column_mapping(path: str | Path) -> ColumnMapping:
    """Load a ColumnMapping from JSON."""
    raw = json.loads(Path(path).read_text())
    return ColumnMapping(**raw)


# ---------------------------------------------------------------------------
# Pattern resolution
# ---------------------------------------------------------------------------

def _resolve_spec(spec: str | list[str], columns: list[str]) -> list[str]:
    """Expand a column spec (scalar, list, or pattern) against actual columns."""
    if isinstance(spec, list):
        return [c for c in spec if c in columns]
    if not spec:
        return []
    if "*" in spec or "##" in spec:
        regex = spec.replace("##", r"\d{1,2}").replace("*", r".*")
        pat = re.compile(f"^{regex}$", re.IGNORECASE)
        return sorted([c for c in columns if pat.match(c)])
    if spec in columns:
        return [spec]
    return []


def _resolve_all(mapping: ColumnMapping, columns: list[str]) -> dict[str, list[str]]:
    """Resolve all multi-valued column specs in a ColumnMapping."""
    return {
        attr: _resolve_spec(getattr(mapping, attr), columns)
        for attr in (
            "author_names", "author_affiliations", "author_departments",
            "author_emails", "pref_columns",
        )
    }


# ---------------------------------------------------------------------------
# Paper loading
# ---------------------------------------------------------------------------

def load_papers(csv_path: str | Path, mapping: ColumnMapping) -> list[Paper]:
    """Load papers from a CSV file using the given column mapping."""
    enc = _detect_encoding(csv_path, mapping.encoding)
    df = pd.read_csv(
        csv_path,
        sep=mapping.separator,
        encoding=enc,
        dtype=str,
        keep_default_na=False,
    )
    # Strip \r from column names (Windows line endings)
    df.columns = [c.strip() for c in df.columns]

    resolved = _resolve_all(mapping, list(df.columns))
    name_cols = resolved["author_names"]
    aff_cols = resolved["author_affiliations"]
    dep_cols = resolved["author_departments"]
    email_cols = resolved["author_emails"]
    pref_cols = resolved["pref_columns"]

    papers: list[Paper] = []
    for _, row in df.iterrows():
        # Build authors – zip across name/aff/dep/email columns
        max_auth = max(len(name_cols), 1)
        authors: list[Author] = []
        for i in range(max_auth):
            name = row.get(name_cols[i], "") if i < len(name_cols) else ""
            if not name or name == "NULL":
                continue
            aff = row.get(aff_cols[i], "") if i < len(aff_cols) else ""
            dep = row.get(dep_cols[i], "") if i < len(dep_cols) else ""
            eml = row.get(email_cols[i], "") if i < len(email_cols) else ""
            if aff == "NULL":
                aff = ""
            if dep == "NULL":
                dep = ""
            if eml == "NULL":
                eml = ""
            name = _fix_mojibake(name)
            aff = _fix_mojibake(aff)
            dep = _fix_mojibake(dep)
            authors.append(Author(name=name, affiliation=aff, department=dep, email=eml))

        # Preferences
        prefs: list[int] = []
        for pc in pref_cols:
            val = row.get(pc, "")
            if val and val != "NULL":
                try:
                    prefs.append(int(val))
                except ValueError:
                    pass

        pid_val = row.get(mapping.paper_id, "0")
        try:
            pid = int(pid_val)
        except ValueError:
            pid = 0

        comment_val = row.get(mapping.comment, "")
        if comment_val == "NULL":
            comment_val = ""

        papers.append(Paper(
            paper_id=pid,
            title=_fix_mojibake(row.get(mapping.title, "")),
            authors=authors,
            corr_email=row.get(mapping.corr_email, ""),
            pref_ids=prefs,
            comment=_fix_mojibake(comment_val),
        ))

    return papers


# ---------------------------------------------------------------------------
# Topic loading
# ---------------------------------------------------------------------------

def load_topics(
    csv_path: str | Path,
    id_col: str = "pref_id",
    name_col: str = "topic name",
    sep: str = ";",
) -> list[Topic]:
    """Load topics from a CSV file."""
    df = pd.read_csv(csv_path, sep=sep, dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    topics: list[Topic] = []
    for _, row in df.iterrows():
        tid = int(row[id_col])
        topics.append(Topic(topic_id=tid, name=row[name_col]))
    return topics


def generate_default_topics(n: int) -> list[Topic]:
    return [Topic(topic_id=i + 1, name=f"Topic {i + 1}") for i in range(n)]


# ---------------------------------------------------------------------------
# Room loading
# ---------------------------------------------------------------------------

def load_rooms(
    csv_path: str | Path,
    id_col: str = "room_id",
    name_col: str = "room_name",
    capacity_col: str = "capacity",
    sep: str = ";",
) -> list[Room]:
    enc = _detect_encoding(csv_path, "utf-8")
    df = pd.read_csv(csv_path, sep=sep, dtype=str, keep_default_na=False,
                      encoding=enc)
    df.columns = [c.strip() for c in df.columns]
    has_id = id_col in df.columns
    rooms: list[Room] = []
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        cap = 0
        if capacity_col in df.columns:
            try:
                cap = int(row[capacity_col])
            except ValueError:
                pass
        rid = int(row[id_col]) if has_id else idx
        rooms.append(Room(
            room_id=rid,
            name=_fix_mojibake(row[name_col]),
            capacity=cap,
        ))
    return rooms


def generate_default_rooms(n: int) -> list[Room]:
    return [Room(room_id=i + 1, name=f"Room {i + 1}") for i in range(n)]


# ---------------------------------------------------------------------------
# Chair loading
# ---------------------------------------------------------------------------

def load_chairs(
    csv_path: str | Path,
    sep: str = ";",
) -> list[Chair]:
    """Load chairs from CSV.

    Supports two formats:
      - Simple: ``chair_id;chair_name``
      - Extended: ``chair_id;lastname;firstname;email;position;arrival;departure``
    """
    enc = _detect_encoding(csv_path, "utf-8")
    df = pd.read_csv(csv_path, sep=sep, dtype=str, keep_default_na=False,
                      encoding=enc)
    df.columns = [c.strip() for c in df.columns]

    has_lastname = "lastname" in df.columns
    has_name = "chair_name" in df.columns
    has_arrival = "arrival" in df.columns
    has_departure = "departure" in df.columns
    has_email = "email" in df.columns

    chairs: list[Chair] = []
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        # ID
        cid = int(row["chair_id"]) if "chair_id" in df.columns else idx

        # Name
        if has_lastname:
            first = _fix_mojibake(row.get("firstname", ""))
            last = _fix_mojibake(row.get("lastname", ""))
            name = f"{first} {last}".strip()
        elif has_name:
            name = _fix_mojibake(row["chair_name"])
        else:
            name = f"Chair {idx}"

        email = row.get("email", "") if has_email else ""
        arrival = int(row["arrival"]) if has_arrival else 1
        departure = int(row["departure"]) if has_departure else 999

        chairs.append(Chair(
            chair_id=cid,
            name=name,
            email=email,
            arrival_day=arrival,
            departure_day=departure,
        ))
    return chairs


def generate_default_chairs(n: int) -> list[Chair]:
    return [Chair(chair_id=i + 1, name=f"Chair {i + 1}") for i in range(n)]


# ---------------------------------------------------------------------------
# Constraint list (plain text file, one constraint per line)
# ---------------------------------------------------------------------------

def load_constraint_lines(path: str | Path) -> list[str]:
    """Load constraint strings from a text file (one per line, # = comment)."""
    lines: list[str] = []
    for raw in Path(path).read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines
