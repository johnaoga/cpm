"""Output the conference programme in Markdown, LaTeX, or CMS CSV format."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from .models import Paper, Program, Session, SlotKind, TimeSlot, build_topic_display_names


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def program_to_markdown(program: Program) -> str:
    """Render the full programme as Markdown."""
    topic_names = build_topic_display_names(program)
    lines: list[str] = []
    lines.append("# Conference Programme\n")

    for day_prog in program.days:
        lines.append(f"## Day {day_prog.day}\n")

        for slot in day_prog.slots:
            ts: TimeSlot = slot["time_slot"]
            sessions: list[Session] = slot["sessions"]

            if ts.kind in (SlotKind.BREAK, SlotKind.LUNCH, SlotKind.DINNER):
                lines.append(f"### {ts.start}–{ts.end}  {ts.label}\n")
                continue

            if ts.kind == SlotKind.PLENARY:
                extra = ""
                if ts.speaker:
                    extra += f" — *{ts.speaker}*"
                if ts.chair:
                    extra += f" (Chair: {ts.chair})"
                lines.append(f"### {ts.start}–{ts.end}  {ts.label}{extra} *(reserved)*\n")
                continue

            # Session slot
            lines.append(f"### {ts.start}–{ts.end}  Sessions\n")

            for sess in sessions:
                room_str = f" — *{sess.room.name}*" if sess.room else ""
                tn = topic_names.get(sess.session_id, sess.topic.name if sess.topic else "")
                topic_str = f" [{tn}]" if tn else ""
                chair_str = f" (Chair: {sess.chair.name})" if sess.chair else ""
                lines.append(
                    f"#### {sess.session_id}{topic_str}{room_str}{chair_str}\n"
                )

                if not sess.papers:
                    lines.append("*No papers assigned.*\n")
                else:
                    for p in sess.papers:
                        authors = ", ".join(a.name for a in p.authors)
                        lines.append(f"- **{p.title}**  ")
                        lines.append(f"  {authors}\n")

        lines.append("---\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------

def _tex_escape(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def program_to_latex(program: Program) -> str:
    """Render the full programme as a standalone LaTeX document."""
    lines: list[str] = []
    lines.append(r"\documentclass[a4paper,11pt]{article}")
    lines.append(r"\usepackage[utf8]{inputenc}")
    lines.append(r"\usepackage[T1]{fontenc}")
    lines.append(r"\usepackage{booktabs}")
    lines.append(r"\usepackage{longtable}")
    lines.append(r"\usepackage{geometry}")
    lines.append(r"\geometry{margin=2cm}")
    lines.append(r"\usepackage{enumitem}")
    lines.append(r"\usepackage{titlesec}")
    lines.append(r"\titleformat{\section}{\Large\bfseries}{Day~\thesection}{1em}{}")
    lines.append(r"\begin{document}")
    lines.append(r"\begin{center}")
    lines.append(r"{\LARGE\bfseries Conference Programme}\\[1em]")
    lines.append(r"\end{center}")
    lines.append("")

    topic_names = build_topic_display_names(program)

    for day_prog in program.days:
        lines.append(f"\\section*{{Day {day_prog.day}}}")
        lines.append("")

        for slot in day_prog.slots:
            ts: TimeSlot = slot["time_slot"]
            sessions: list[Session] = slot["sessions"]

            if ts.kind in (SlotKind.BREAK, SlotKind.LUNCH, SlotKind.DINNER):
                lines.append(
                    f"\\subsection*{{{ts.start}--{ts.end} \\quad "
                    f"\\textit{{{_tex_escape(ts.label)}}}}}"
                )
                lines.append("")
                continue

            if ts.kind == SlotKind.PLENARY:
                extra = ""
                if ts.speaker:
                    extra += f" -- {_tex_escape(ts.speaker)}"
                if ts.chair:
                    extra += f" (Chair: {_tex_escape(ts.chair)})"
                lines.append(
                    f"\\subsection*{{{ts.start}--{ts.end} \\quad "
                    f"{_tex_escape(ts.label)}{extra} (reserved)}}"
                )
                lines.append("")
                continue

            lines.append(f"\\subsection*{{{ts.start}--{ts.end} \\quad Sessions}}")
            lines.append("")

            for sess in sessions:
                tn = topic_names.get(sess.session_id, sess.topic.name if sess.topic else "")
                topic_str = (
                    f" -- {_tex_escape(tn)}" if tn else ""
                )
                room_str = (
                    f" \\textit{{{_tex_escape(sess.room.name)}}}" if sess.room else ""
                )
                chair_str = (
                    f" (Chair: {_tex_escape(sess.chair.name)})" if sess.chair else ""
                )
                lines.append(
                    f"\\paragraph{{{_tex_escape(sess.session_id)}"
                    f"{topic_str}{room_str}{chair_str}}}"
                )

                if sess.papers:
                    lines.append(r"\begin{itemize}[leftmargin=*]")
                    for p in sess.papers:
                        authors = ", ".join(
                            _tex_escape(a.name) for a in p.authors
                        )
                        lines.append(
                            f"  \\item \\textbf{{{_tex_escape(p.title)}}} "
                            f"\\\\ {authors}"
                        )
                    lines.append(r"\end{itemize}")
                else:
                    lines.append(r"\emph{No papers assigned.}")
                lines.append("")

        lines.append(r"\bigskip\hrule\bigskip")
        lines.append("")

    lines.append(r"\end{document}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Convenience writer
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CMS CSV output
# ---------------------------------------------------------------------------

def _time_to_seconds(t: str) -> int:
    """Convert HH:MM to seconds since midnight."""
    parts = t.replace(".", ":").split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60


def _collect_session_slots(program: Program) -> list[tuple[Session, TimeSlot, int]]:
    """Collect (session, timeslot, day) triples for all SESSION slots."""
    result = []
    for day_prog in program.days:
        for slot in day_prog.slots:
            ts: TimeSlot = slot["time_slot"]
            if ts.kind != SlotKind.SESSION:
                continue
            for sess in slot["sessions"]:
                result.append((sess, ts, day_prog.day))
    return result


def program_to_cms_sessions(program: Program, sep: str = ";") -> str:
    """Generate a CMS-style sessions CSV.

    Columns: session_id, name, room, topic, chair, day, begin
    (begin is in seconds since midnight).
    """
    topic_names = build_topic_display_names(program)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, quoting=csv.QUOTE_ALL)
    writer.writerow(["session_id", "name", "room", "topic", "chair", "day", "begin"])

    for sess, ts, day in _collect_session_slots(program):
        sid = sess.session_id
        name = sid
        room = sess.room.name if sess.room else ""
        topic = topic_names.get(sess.session_id, sess.topic.name if sess.topic else "")
        chair = sess.chair.name if sess.chair else ""
        begin = _time_to_seconds(ts.start)
        writer.writerow([sid, name, room, topic, chair, str(day), str(begin)])

    return buf.getvalue()


def program_to_cms_presentations(
    program: Program, presentation_duration: int = 1200, sep: str = ";"
) -> str:
    """Generate a CMS-style presentations CSV.

    Columns: presentation_id, session_id, number, paper_id, duration
    (duration is in seconds).
    """
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, quoting=csv.QUOTE_ALL)
    writer.writerow(["presentation_id", "session_id", "number", "paper_id", "duration"])

    pres_id = 1
    for sess, ts, _day in _collect_session_slots(program):
        for idx, paper in enumerate(sess.papers, start=1):
            writer.writerow([
                str(pres_id), sess.session_id, str(idx),
                str(paper.paper_id), str(presentation_duration),
            ])
            pres_id += 1

    return buf.getvalue()


def write_cms_csvs(
    program: Program,
    sessions_path: str | Path,
    presentations_path: str | Path,
    presentation_duration: int = 1200,
    sep: str = ";",
) -> None:
    """Write both CMS CSV files."""
    Path(sessions_path).write_text(
        program_to_cms_sessions(program, sep=sep), encoding="utf-8"
    )
    Path(presentations_path).write_text(
        program_to_cms_presentations(program, presentation_duration, sep=sep),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Convenience writer
# ---------------------------------------------------------------------------

def write_program(program: Program, path: str | Path, fmt: str = "md") -> None:
    """Write the programme to *path* in the given format ('md' or 'latex')."""
    if fmt == "latex":
        text = program_to_latex(program)
    else:
        text = program_to_markdown(program)
    Path(path).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Unassigned papers
# ---------------------------------------------------------------------------

def _assigned_paper_ids(program: Program) -> set[int]:
    """Return the set of paper IDs that appear in any session of *program*."""
    ids: set[int] = set()
    for day_prog in program.days:
        for slot in day_prog.slots:
            for sess in slot.get("sessions", []):
                if isinstance(sess, Session):
                    for p in sess.papers:
                        ids.add(p.paper_id)
    return ids


def find_unassigned_papers(
    program: Program, papers: list[Paper],
) -> list[Paper]:
    """Return papers that are not assigned to any session in *program*."""
    assigned = _assigned_paper_ids(program)
    return [p for p in papers if p.paper_id not in assigned]


def write_unassigned_papers(
    program: Program,
    papers: list[Paper],
    path: str | Path,
    sep: str = ";",
) -> list[Paper]:
    """Write unassigned papers to a CSV file.

    Columns: paper_id, title, authors, affiliations, emails, preferences, comment

    Returns the list of unassigned papers.
    """
    unassigned = find_unassigned_papers(program, papers)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=sep, quoting=csv.QUOTE_ALL)
    writer.writerow([
        "paper_id", "title", "authors", "affiliations", "emails",
        "preferences", "comment",
    ])
    for p in unassigned:
        authors = " | ".join(a.name for a in p.authors if a.name)
        affiliations = " | ".join(a.affiliation for a in p.authors if a.affiliation)
        emails = " | ".join(a.email for a in p.authors if a.email)
        prefs = ", ".join(str(pid) for pid in p.pref_ids)
        writer.writerow([
            p.paper_id, p.title, authors, affiliations, emails,
            prefs, p.comment,
        ])

    out.write_text(buf.getvalue(), encoding="utf-8")
    return unassigned
