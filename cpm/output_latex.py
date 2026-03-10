"""Generate a full LaTeX project folder matching the Benelux boa2023 style.

The output folder contains:
  - main.tex            (the master document)
  - commands.tex        (custom LaTeX commands)
  - front.tex           (cover page with conference metadata)
  - program.tex         (programmatic table of contents)
  - day{N}_{name}.tex   (per-day contributed talks)
  - participants.tex    (placeholder for participant list)

A ``latex_config.json`` provides all conference metadata (title, dates,
venue, editors, colours, …).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from .models import Program, SlotKind, TimeSlot, build_topic_display_names

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LaTeX config dataclass
# ---------------------------------------------------------------------------

@dataclass
class LaTeXConfig:
    """Conference metadata used to fill the LaTeX templates."""
    conference_title: str = "Conference"
    conference_subtitle: str = "on Systems and Control"
    edition: str = "1st"
    date_text: str = "January 1 -- 3, 2025"
    venue: str = "City, Country"
    document_title: str = "Book of Abstracts"
    editors: str = ""
    institution: str = ""
    institution_address: str = ""
    isbn: str = ""
    sponsors_text: str = ""
    logo_file: str = ""
    header_left: str = ""
    header_right: str = "Book of Abstracts"
    day_names: list[str] = field(default_factory=list)
    day_dates: list[str] = field(default_factory=list)
    colors: dict[str, str] = field(default_factory=lambda: {
        "daybox": "1,.2,.2",
        "plebox": ".4,0,.8",
        "sesbox": ".8,.8,1",
    })
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        d = self.__dict__.copy()
        Path(path).write_text(json.dumps(d, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: str | Path) -> "LaTeXConfig":
        raw = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__})

    def day_name(self, day: int) -> str:
        if self.day_names and day - 1 < len(self.day_names):
            return self.day_names[day - 1]
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return weekdays[(day - 1) % 7]

    def day_date(self, day: int) -> str:
        if self.day_dates and day - 1 < len(self.day_dates):
            return self.day_dates[day - 1]
        return ""

    def full_day_heading(self, day: int) -> str:
        name = self.day_name(day)
        date = self.day_date(day)
        if date:
            return f"{name}, {date}"
        return f"{name} — Day {day}"


# ---------------------------------------------------------------------------
# TeX escaping
# ---------------------------------------------------------------------------

_TEX_REPLACEMENTS = {
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


def _esc(text: str) -> str:
    for old, new in _TEX_REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


# ---------------------------------------------------------------------------
# Template generators
# ---------------------------------------------------------------------------

def _gen_commands() -> str:
    """Generate commands.tex (custom macros for the programme)."""
    return r"""\newcommand{\euros}[1]{€ #1}

\newcommand{\dayheading}[1]{%
\vfill \newpage \setlength{\myboxwidth}{\columnwidth}
\addtolength{\myboxwidth}{-2\fboxsep}
\addtolength{\myboxwidth}{-0.8pt}
\fcolorbox{fdaybox}{daybox}{\begin{minipage}[t]%
{\myboxwidth}\color{day}\centerline{\textbf{#1}}
\end{minipage}}\vfil}

\newcommand{\pleheading}[6]{%
\setlength{\myboxwidth}{\columnwidth}
\addtolength{\myboxwidth}{-2\fboxsep}
\addtolength{\myboxwidth}{-0.8pt}
\fcolorbox{fplebox}{plebox}{\begin{minipage}[t]%
{\myboxwidth}\color{ple}\textbf{#1}\hfill\textbf{#2}\\
\centerline{\textbf{#3}}\\
\centerline{\textbf{#4}}\\\textbf{Chair: #5}
\hfill\textbf{#6}\end{minipage}}\vfil}

\newcommand{\sesheading}[5]{%
\setlength{\myboxwidth}{\columnwidth}
\addtolength{\myboxwidth}{-2\fboxsep}
\addtolength{\myboxwidth}{-0.8pt}
\fcolorbox{fsesbox}{sesbox}{\begin{minipage}[t]%
{\myboxwidth}\color{ses}\textbf{#1}\hfill\textbf{#2}\\
\centerline{\textbf{#3}}\\\textbf{Chair: #4}
\hfill\textbf{#5}\end{minipage}}\vfil}

\makeatletter
\renewcommand{\@pnumwidth}{1.87em}
\newcommand{\putplentitle}[2]{\@dottedtocline{0}{0em}{0em}%
{\textit{#1\/}}{\ifthenelse{\equal{#2}{}}{}{\hyperlink{#2}{\pageref*{#2}}}}}
\newcommand{\puttalktitle}[1]{\@dottedtocline{0}{0em}{0em}%
{\textit{#1\/}}{\hyperlink{}{}}
\addtocounter{sp}{1}} \makeatother

\newcommand{\putplen}[3]{%
\parbox{\columnwidth}{\putplentitle{#1}{#3}#2\par}\vfil}

\newcommand{\puttalk}[9]{%
\parbox{\columnwidth}{\textbf{#1}
\puttalktitle{#2}
#3\hfill{#4}\par%
\ifthenelse{\equal{#5}{}}{}{#5\hfill{#6}\par%
\ifthenelse{\equal{#7}{}}{}{#7\hfill{#8}\par%
\ifthenelse{\equal{#9}{}}{}{#9\par}}}}\vfil}

\newcommand{\putpart}[5]{#1 #2\\ #3\\ #4\\
\href{mailto:#5}{#5}\vfil}
"""


def _gen_front(lcfg: LaTeXConfig) -> str:
    """Generate front.tex (cover page)."""
    logo_line = ""
    if lcfg.logo_file:
        logo_line = f"\\includegraphics[height=2.5cm]{{{lcfg.logo_file}}}"

    sponsors_block = ""
    if lcfg.sponsors_text:
        sponsors_block = f"The {_esc(lcfg.edition)} {_esc(lcfg.conference_title)} {_esc(lcfg.conference_subtitle)} is sponsored by\\\\\n\n{logo_line}"

    editors_line = ""
    if lcfg.editors:
        editors_line = f"{{\\large{{\\textbf{{{_esc(lcfg.editors)}}}}}}}\n"

    isbn_line = ""
    if lcfg.isbn:
        isbn_line = f"ISBN: {_esc(lcfg.isbn)}"

    inst_block = ""
    if lcfg.institution:
        inst_block = f"{_esc(lcfg.institution)}\\\\\n{_esc(lcfg.institution_address)}"

    return f"""%%%
%%%    -- Cover page
%%%

\\thispagestyle{{empty}}

\\begin{{center}}
\\vspace*{{4cm}}
{{\\Huge \\textbf{{{_esc(lcfg.edition)} {_esc(lcfg.conference_title)}}}}}
\\bigskip\\bigskip

{{\\Huge \\textbf{{{_esc(lcfg.conference_subtitle)}}}}}\\\\
\\vspace{{4cm}}

{{\\Large \\textbf{{{_esc(lcfg.date_text)}}}}}
\\bigskip

{{\\Large \\textbf{{{_esc(lcfg.venue)}}}}}
\\vspace{{4cm}}

{{\\Huge \\textbf{{{_esc(lcfg.document_title)}}}}}
\\end{{center}}

\\vfill
\\pagebreak

%%%
%%%    -- Front material
%%%

\\thispagestyle{{empty}}
{sponsors_block}
\\vfill
{editors_line}
{{\\large{{\\textbf{{{_esc(lcfg.document_title)} - {_esc(lcfg.edition)} {_esc(lcfg.conference_title)} {_esc(lcfg.conference_subtitle)}}}}}}}

\\bigskip
{inst_block}

\\medskip
All rights reserved. No part of the publication may be reproduced
in any form by print, photo print, microfilm or by any other means
without prior permission in writing from the publisher.

\\medskip
{isbn_line}
\\vspace*{{.5cm}} \\cleardoublepage
"""


def _gen_main(
    lcfg: LaTeXConfig,
    day_files: list[str],
    *,
    with_comments: bool = False,
    with_abstracts: bool = False,
) -> str:
    """Generate main.tex (master document)."""
    header_left = _esc(lcfg.header_left or f"{lcfg.edition} {lcfg.conference_title}")
    header_right = _esc(lcfg.header_right)
    pdf_title = f"{lcfg.document_title} {lcfg.edition} {lcfg.conference_title}"

    col = lcfg.colors
    daybox = col.get("daybox", "1,.2,.2")
    plebox = col.get("plebox", ".4,0,.8")
    sesbox = col.get("sesbox", ".8,.8,1")

    comments_block = ""
    if with_comments:
        comments_block = (
            "\n%% -- COMMENTS (general info + programme tables) -- %%\n"
            "\\onecolumn\n"
            "\\input{comments}\n"
            "\\cleardoublepage \\mbox{} \\vspace*{6cm}\n"
        )

    abstracts_block = ""
    if with_abstracts:
        abstracts_block = (
            "\n%% -- ABSTRACTS -- %%\n"
            "\\onecolumn \\cleardoublepage \\mbox{} \\vspace*{6cm}\n"
            "\\begin{center}\n"
            "\\Huge\\textbf{Part 3\\\\[2ex] Abstracts}\n"
            "\\end{center}\n"
            "\\cleardoublepage\n"
            "\\input{abstracts}\n"
        )

    return f"""\\documentclass[a4paper]{{book}}
%%
%% -- USED PACKAGES --
%%
\\usepackage{{amsmath,amsfonts,amssymb}}
\\usepackage[pdftex]{{graphicx}}
\\usepackage[table,fixpdftex]{{xcolor}}
\\usepackage{{latexsym}}
\\usepackage{{ifthen}}
\\usepackage{{tabularx}}
\\usepackage{{lscape}}
\\usepackage{{fancyhdr}}
\\usepackage{{pdfpages}}
\\usepackage[]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{amstext}}
\\usepackage[pdftex]{{hyperref}}

%%
%% -- COLOR DEFINITIONS
%%
\\newcommand{{\\RED}}[1]{{{{\\textcolor{{red}}{{#1}}}}}}
\\definecolor{{bmscred}}{{rgb}}{{{daybox}}}
\\definecolor{{bmscdark}}{{rgb}}{{{plebox}}}
\\definecolor{{bmscblue}}{{rgb}}{{{sesbox}}}
\\definecolor{{daybox}}{{rgb}}{{{daybox}}}
\\definecolor{{plebox}}{{rgb}}{{{plebox}}}
\\definecolor{{sesbox}}{{rgb}}{{{sesbox}}}
\\definecolor{{fdaybox}}{{rgb}}{{{daybox}}}
\\definecolor{{fplebox}}{{rgb}}{{{plebox}}}
\\definecolor{{fsesbox}}{{rgb}}{{{sesbox}}}
\\definecolor{{day}}{{gray}}{{0}}
\\definecolor{{ple}}{{gray}}{{1}}
\\definecolor{{ses}}{{gray}}{{0}}

%%
%% -- WIDTHS
%%
\\newlength{{\\myboxwidth}}
\\newlength{{\\colw}}
\\setlength{{\\colw}}{{244mm}}

%%
%% -- HYPERREF
%%
\\hypersetup{{pdftitle={{{_esc(pdf_title)}}},
pdfsubject={{{_esc(lcfg.conference_title)}}},
pdfkeywords={{}}, pdfcreator={{\\LaTeX}}, colorlinks=true}}

%%
%% -- COMMANDS
%%
\\input{{commands}}

%%
%% -- VARIABLES
%%
\\newcounter{{sp}}
\\setcounter{{sp}}{{21}}
\\newcounter{{a}}

%%
%% -- PAGE LAYOUT
%%
\\topmargin -8.9mm \\headheight 5mm \\headsep 5mm \\textwidth 178mm
\\textheight 244mm \\columnsep 8mm \\oddsidemargin -9.4mm
\\evensidemargin -9.4mm
\\parindent 0em
\\parskip 1ex plus 0.1ex minus 0.1ex
\\pagestyle{{fancy}} \\fancyhead[LE,RO]{{\\rmfamily {header_right}}}
\\fancyhead[LO,RE]{{\\rmfamily {header_left}}} \\fancyfoot[C]{{\\rmfamily\\thepage}}
\\renewcommand{{\\headrulewidth}}{{0.4pt}}
\\renewcommand{{\\footrulewidth}}{{0pt}}
\\frenchspacing \\sloppy

\\begin{{document}}

%% -- FRONT -- %%
\\input{{front}}
\\cleardoublepage \\mbox{{}} \\vspace*{{6cm}}

%% -- PROGRAM -- %%
\\begin{{center}}
\\Huge\\textbf{{Part 1\\\\[2ex] Programmatic Table of Contents}}
\\end{{center}}

\\hypertarget{{P:1}}{{}} \\label{{P:1}} \\twocolumn \\cleardoublepage
\\pagestyle{{fancy}}

\\input{{program}}

\\medskip\\nopagebreak

\\putplen{{Part 1: \\ \\ Programmatic Table of Contents}}{{Overview of scientific program}}{{P:1}}

\\medskip\\nopagebreak

\\putplen{{Part 2: \\ \\ List of Participants}}{{Alphabetical list}}{{P:4}}

\\putplen{{Part 3: \\ \\ Organizational Comments}}{{Comments, overview program, map}}{{P:5}}

\\nopagebreak \\vfill
%% -- END PROGRAM -- %%

{abstracts_block}

%% -- PARTICIPANTS -- %%
\\onecolumn \\cleardoublepage \\mbox{{}} \\vspace*{{6cm}}
\\begin{{center}}
\\Huge\\textbf{{Part 2\\\\[2ex] List of Participants}}
\\end{{center}}
\\hypertarget{{P:4}}{{}} \\label{{P:4}} \\twocolumn \\cleardoublepage

\\input{{participants}}
\\nopagebreak \\vfill

\\newpage

%% -- END OF PARTICIPANTS -- %%

{comments_block}

\\end{{document}}
"""


def _gen_program_tex(program: Program, lcfg: LaTeXConfig, day_file_map: dict[int, str]) -> str:
    """Generate program.tex — the programmatic table of contents.

    Interleaves plenaries and \\input{dayN_period} in correct time order,
    matching the boa2023 style.
    """
    lines: list[str] = []

    for day_prog in program.days:
        day_num = day_prog.day
        heading = lcfg.full_day_heading(day_num)
        lines.append(f"\\dayheading{{{_esc(heading)}}}")
        lines.append("")
        lines.append("\\medskip\\nopagebreak")
        lines.append("")

        # Group consecutive session slots into periods and interleave
        # with plenaries in correct time order
        pending_sessions = False
        period_idx = 0

        for slot in day_prog.slots:
            ts: TimeSlot = slot["time_slot"]

            if ts.kind in (SlotKind.BREAK, SlotKind.LUNCH, SlotKind.DINNER):
                # Flush pending sessions before a break
                if pending_sessions:
                    fname = f"day{day_num}_p{period_idx}"
                    if day_num in day_file_map:
                        fname = f"{day_file_map[day_num]}_p{period_idx}"
                    lines.append(f"\\input{{{fname}}}")
                    lines.append("")
                    pending_sessions = False
                    period_idx += 1
                continue

            if ts.kind == SlotKind.PLENARY:
                # Flush pending sessions before a plenary
                if pending_sessions:
                    fname = f"day{day_num}_p{period_idx}"
                    if day_num in day_file_map:
                        fname = f"{day_file_map[day_num]}_p{period_idx}"
                    lines.append(f"\\input{{{fname}}}")
                    lines.append("")
                    pending_sessions = False
                    period_idx += 1

                # Render plenary heading
                # Extract room from the session if available
                sessions = slot.get("sessions", [])
                room_name = ""
                if sessions and hasattr(sessions[0], 'room') and sessions[0].room:
                    room_name = sessions[0].room.name
                speaker = _esc(ts.speaker) if ts.speaker else ""
                chair_str = f"{_esc(ts.chair)}" if ts.chair else ""
                plenary_name = lcfg.extra.get("plenary_name", "Plenary")
                label = ts.label or ""
                trunc = lcfg.extra.get("truncate_plenary_title")
                if trunc and isinstance(trunc, int) and len(label) > trunc:
                    label = label[:trunc] + "..."
                lines.append(
                    f"\\pleheading{{{_esc(plenary_name)}}}{{{_esc(room_name)}}}"
                    f"{{{_esc(label)}}}{{{speaker}}}"
                    f"{{{chair_str}}}{{{ts.start}--{ts.end}}}"
                )
                lines.append("")
                lines.append("\\medskip\\nopagebreak")
                lines.append("")
                continue

            # SESSION slot — mark as pending
            if ts.kind == SlotKind.SESSION:
                pending_sessions = True

        # Flush any remaining sessions at end of day
        if pending_sessions:
            fname = f"day{day_num}_p{period_idx}"
            if day_num in day_file_map:
                fname = f"{day_file_map[day_num]}_p{period_idx}"
            lines.append(f"\\input{{{fname}}}")
            lines.append("")

    return "\n".join(lines)


def _gen_day_period_tex(
    program: Program, day_num: int, period_idx: int, lcfg: LaTeXConfig
) -> str:
    """Generate a dayN_pM.tex file with sessions and talks for one period.

    A *period* is a contiguous block of SESSION slots between
    plenaries/breaks/lunch within one day.
    """
    topic_names = build_topic_display_names(program)
    lines: list[str] = []
    lines.append(f"%% THIS IS THE PROGRAM DATA FOR DAY {day_num} PERIOD {period_idx}")
    lines.append("%% AUTOMATICALLY GENERATED BY CPM")
    lines.append("")

    day_prog = None
    for dp in program.days:
        if dp.day == day_num:
            day_prog = dp
            break
    if day_prog is None:
        return "\n".join(lines)

    # Iterate and track period index
    cur_period = 0
    in_sessions = False
    for slot in day_prog.slots:
        ts = slot["time_slot"]
        sessions = slot["sessions"]

        if ts.kind == SlotKind.SESSION:
            if not in_sessions and cur_period > 0:
                pass  # already advanced
            in_sessions = True

            if cur_period != period_idx:
                continue

            for sess in sessions:
                room_name = sess.room.name if sess.room else ""
                topic_name = topic_names.get(sess.session_id, sess.topic.name if sess.topic else "")
                chair_name = sess.chair.name if sess.chair else ""

                exact_pres = lcfg.extra.get("exact_presentation_timing", False)
                exact_sess = lcfg.extra.get("exact_session_timing", False)
                cfg_pres_dur = lcfg.extra.get("presentation_duration_min", 20)

                if exact_pres:
                    pres_dur = cfg_pres_dur
                else:
                    pres_dur = 20
                    try:
                        if len(sess.papers) > 0 and ts.duration_minutes > 0:
                            pres_dur = ts.duration_minutes // len(sess.papers)
                    except Exception:
                        pass

                # Compute session time range
                if exact_sess and sess.papers:
                    exact_end_min = _time_to_min(ts.start) + len(sess.papers) * pres_dur
                    time_range = f"{ts.start}-{_fmt_min(exact_end_min).replace('.', ':')}"
                else:
                    time_range = f"{ts.start}-{ts.end}"

                lines.append(
                    f"\\sesheading{{{_esc(sess.session_id)}}}{{{_esc(room_name)}}}"
                )
                lines.append(f"{{{_esc(topic_name)}}}")
                lines.append(f"{{{_esc(chair_name)}}}{{{time_range}}}")
                lines.append("")
                lines.append("\\medskip\\nopagebreak")
                lines.append("")

                if not sess.papers:
                    continue

                for idx, paper in enumerate(sess.papers):
                    start_min = _time_to_min(ts.start) + idx * pres_dur
                    end_min = start_min + pres_dur
                    talk_start = _fmt_min(start_min)
                    talk_end = _fmt_min(end_min)
                    talk_id = f"{sess.session_id}-{idx + 1}"

                    authors = paper.authors
                    a1_name = _esc(authors[0].name) if len(authors) > 0 else ""
                    a1_aff = _esc(authors[0].affiliation) if len(authors) > 0 and authors[0].affiliation else ""
                    a2_name = _esc(authors[1].name) if len(authors) > 1 else ""
                    a2_aff = _esc(authors[1].affiliation) if len(authors) > 1 and authors[1].affiliation else ""
                    a3_name = _esc(authors[2].name) if len(authors) > 2 else ""
                    a3_aff = _esc(authors[2].affiliation) if len(authors) > 2 and authors[2].affiliation else ""
                    speaker = _esc(authors[0].name) if len(authors) > 0 else ""

                    lines.append(
                        f"\\puttalk{{{_esc(talk_id)}\\hfill {talk_start}-{talk_end}}}"
                    )
                    lines.append(f"{{{_esc(paper.title)}}}")
                    lines.append(f"{{{a1_name}}}{{{a1_aff}}}")
                    lines.append(f"{{{a2_name}}}{{{a2_aff}}}")
                    lines.append(f"{{{a3_name}}}{{{a3_aff}}}")
                    lines.append(f"{{{speaker}}}")
                    lines.append("")

        else:
            # Non-session: advance period counter if we were in sessions
            if in_sessions:
                cur_period += 1
                in_sessions = False

    lines.append("")
    return "\n".join(lines)


def _count_session_periods(day_prog) -> int:
    """Count the number of contiguous session-slot groups in a day."""
    count = 0
    in_sessions = False
    for slot in day_prog.slots:
        if slot["time_slot"].kind == SlotKind.SESSION:
            if not in_sessions:
                count += 1
                in_sessions = True
        else:
            in_sessions = False
    return count


def _gen_participants(papers: list) -> str:
    """Generate participants.tex from paper author data.

    Each unique author appears once, sorted alphabetically by last name.
    Format: \\putpart{}{Name}{Affiliation}{}{email}
    """
    seen: dict[str, tuple[str, str, str]] = {}  # name -> (name, affil, email)
    for p in papers:
        for a in p.authors:
            key = a.name.strip().lower()
            if key and key not in seen:
                seen[key] = (a.name.strip(), a.affiliation.strip(), a.email.strip())

    # Sort by last name (last word of name)
    entries = sorted(seen.values(), key=lambda t: t[0].split()[-1].lower() if t[0] else "")

    lines = ["%% Participant list — automatically generated by CPM"]
    for name, affil, email in entries:
        lines.append(
            f"\\putpart{{}}{{{_esc(name)}}}{{{_esc(affil)}}}{{}}{{{_esc(email)}}}"
        )
    return "\n".join(lines)


def _gen_abstracts(program: Program, pdf_template: str) -> str:
    r"""Generate abstracts.tex — ``\includepdf`` for every paper in programme order.

    *pdf_template* is a path pattern containing ``<id>`` which is replaced by
    the paper id.  Example: ``"pdf/bmsc2025_<id>.pdf"``.
    """
    lines = [
        "%% THIS LIST OF ALL ABSTRACTS IS ORDERED ACCORDING TO THE PROGRAM",
        "%% THE DATA IS AUTOMATICALLY GENERATED BY CPM",
        "%% PLEASE CHECK IT THOROUGHLY",
        "",
    ]
    for dp in program.days:
        for slot in dp.slots:
            for sess in slot.get("sessions", []):
                if not hasattr(sess, "papers"):
                    continue
                for paper in sess.papers:
                    path = pdf_template.replace("<id>", str(paper.paper_id))
                    lines.append(f"\\includepdf{{{path}}}")
    lines.append("")
    return "\n".join(lines)


def _speaker_last_name(paper) -> str:
    """Return the last name of the first author (the presenter)."""
    if not paper.authors:
        return ""
    name = paper.authors[0].name.strip()
    # Last word of the name
    parts = name.split()
    return _esc(parts[-1]) if parts else ""


def _gen_comments(program: Program, lcfg: LaTeXConfig) -> str:
    r"""Generate comments.tex — placeholder text + landscape programme tables.

    The first part is generic boilerplate (welcome, aim, directions, …) that
    the user is expected to customise.  The second part contains auto-generated
    landscape ``tabularx`` tables that give a compact overview of the schedule
    (one table per day).
    """
    topic_names = build_topic_display_names(program)
    lines: list[str] = []

    # ── Placeholder sections (user-editable) ──
    conf = f"{lcfg.edition} {lcfg.conference_title} {lcfg.conference_subtitle}"
    lines.append(r"\section*{Welcome}")
    lines.append("The Organizing Committee has the pleasure of welcoming you to the")
    lines.append(f"\\emph{{{_esc(conf)}}}, at {_esc(lcfg.venue)}.")
    lines.append("")
    lines.append(r"\section*{Aim}")
    lines.append(f"The aim of the {_esc(lcfg.conference_title)} is to promote research activities")
    lines.append("and to enhance cooperation between researchers in the field.")
    lines.append("")
    lines.append(r"\section*{Directions for speakers}")
    lines.append("For a contributed lecture, the available time includes a few minutes for discussion")
    lines.append("and room changes. Please adhere to the indicated schedule.")
    lines.append("In each room LCD projectors are available, as well as HDMI cables.")
    lines.append(r"{\em When using a projector, you have to provide a notebook yourself.}")
    lines.append("")
    lines.append(r"\section*{Website}")
    lines.append("% TODO: Add the conference website URL here.")
    lines.append("")
    lines.append("")

    # ── Auto-generated landscape programme tables ──
    lines.append(r"\setlength\minrowclearance{1pt}")
    lines.append(r"\newcommand{\rr}{\raggedright}")
    lines.append("")

    for dp in program.days:
        day_num = dp.day
        heading = lcfg.full_day_heading(day_num)

        # Collect parallel-session groups for this day.
        # Each group = list of slots that share the same time-slot start.
        # Also gather plenaries, breaks, lunches, dinners.
        ordered_items: list[dict] = []  # {kind, ts, sessions?}

        for slot in dp.slots:
            ts: TimeSlot = slot["time_slot"]
            sessions = slot.get("sessions", [])
            ordered_items.append({
                "kind": ts.kind,
                "ts": ts,
                "sessions": sessions,
            })

        # Determine the maximum number of parallel rooms for this day
        max_rooms = 0
        for item in ordered_items:
            if item["kind"] == SlotKind.SESSION:
                max_rooms = max(max_rooms, len(item["sessions"]))
        if max_rooms == 0:
            max_rooms = 1
        n_cols = max_rooms  # number of room columns

        col_spec = "|".join(["X"] * n_cols)
        lines.append(r"\begin{landscape}")
        lines.append(r"\vfill")
        lines.append(f"\\centerline{{\\large\\textbf{{{_esc(heading)}}}}}")
        lines.append(f"\\begin{{tabularx}}{{\\colw}}{{>{{\\columncolor{{bmscblue}}}}l{col_spec}l|}}")
        lines.append(r"\hline")

        for item in ordered_items:
            ts = item["ts"]
            kind = item["kind"]
            sessions = item["sessions"]
            time_str = f"{ts.start} -- {ts.end}"

            if kind == SlotKind.PLENARY:
                label = ts.label or "Plenary"
                trunc = lcfg.extra.get("truncate_plenary_title")
                if trunc and isinstance(trunc, int) and len(label) > trunc:
                    label = label[:trunc] + "..."
                # Room from session if available
                room_name = ""
                if sessions and hasattr(sessions[0], "room") and sessions[0].room:
                    room_name = sessions[0].room.name
                room_str = f" -- {_esc(room_name)}" if room_name else ""
                mc = n_cols
                # First row: label + room
                lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{{_esc(label)}{room_str}}} & \\\\")
                # Second row: speaker (if available)
                if ts.speaker:
                    lines.append(f"{time_str} & \\multicolumn{{{mc}}}{{c}}{{{_esc(ts.speaker)} -- \\emph{{{_esc(label)}}}}} & \\\\ \\hline")
                else:
                    lines.append(f"{time_str} & \\multicolumn{{{mc}}}{{c}}{{\\emph{{{_esc(label)}}}}} & \\\\ \\hline")

            elif kind in (SlotKind.BREAK, SlotKind.ROOM_CHANGE):
                show_breaks = lcfg.extra.get("comment_show_breaks", True)
                if show_breaks:
                    mc = n_cols
                    label = ts.label or "Coffee Break"
                    lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{}} & \\\\")
                    lines.append(f"{time_str} & \\multicolumn{{{mc}}}{{c}}{{{_esc(label)}}} & \\\\")
                    lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{}} & \\\\ \\hline")

            elif kind == SlotKind.LUNCH:
                show_breaks = lcfg.extra.get("comment_show_breaks", True)
                if show_breaks:
                    mc = n_cols
                    lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{}} & \\\\")
                    lines.append(f"{time_str} & \\multicolumn{{{mc}}}{{c}}{{Lunch}} & \\\\")
                    lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{}} & \\\\ \\hline")

            elif kind == SlotKind.DINNER:
                show_breaks = lcfg.extra.get("comment_show_breaks", True)
                if show_breaks:
                    mc = n_cols
                    lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{}} & \\\\")
                    lines.append(f"{time_str} & \\multicolumn{{{mc}}}{{c}}{{Dinner}} & \\\\")
                    lines.append(f"    & \\multicolumn{{{mc}}}{{c}}{{}} & \\\\ \\hline")

            elif kind == SlotKind.SESSION:
                # Session header row: Room names
                room_cells = []
                sid_cells = []
                topic_cells = []
                for sess in sessions:
                    rn = _esc(sess.room.name) if sess.room else ""
                    room_cells.append(rn)
                    sid_cells.append(_esc(sess.session_id))
                    tn = _esc(topic_names.get(sess.session_id, sess.topic.name if sess.topic else ""))
                    topic_cells.append(f"\\rr \\emph{{{tn}}}")
                # Pad to n_cols
                while len(room_cells) < n_cols:
                    room_cells.append("")
                    sid_cells.append("")
                    topic_cells.append("")

                room_row = " & ".join(room_cells)
                sid_row = " & ".join(sid_cells)
                topic_row = " & ".join(topic_cells)

                lines.append(f"Room & {room_row} & \\\\")
                period_label = sessions[0].session_id[:4] if sessions else ""
                lines.append(f"{_esc(period_label)} & {sid_row} & \\\\")
                lines.append(f"    & {topic_row} & \\\\ \\hline")

                # Show chairs row if configured
                show_chairs = lcfg.extra.get("comment_show_chairs", True)
                if show_chairs:
                    chair_cells = []
                    for sess in sessions:
                        cn = _esc(sess.chair.name) if sess.chair else ""
                        chair_cells.append(cn)
                    while len(chair_cells) < n_cols:
                        chair_cells.append("")
                    chair_row = " & ".join(chair_cells)
                    lines.append(f"Chair & {chair_row} & \\\\ \\hline")

                # Paper rows: one row per presentation time slot
                if sessions:
                    max_papers = max(len(s.papers) for s in sessions) if sessions else 0
                    exact_pres = lcfg.extra.get("exact_presentation_timing", False)
                    cfg_pres_dur = lcfg.extra.get("presentation_duration_min", 20)

                    if exact_pres:
                        pres_dur = cfg_pres_dur
                    else:
                        pres_dur = 20
                        try:
                            if max_papers > 0 and ts.duration_minutes > 0:
                                pres_dur = ts.duration_minutes // max_papers
                        except Exception:
                            pass

                    for pidx in range(max_papers):
                        start_min = _time_to_min(ts.start) + pidx * pres_dur
                        end_min = start_min + pres_dur
                        t_str = f"{_fmt_min(start_min)} -- {_fmt_min(end_min)}"

                        name_cells = []
                        for sess in sessions:
                            if pidx < len(sess.papers):
                                name_cells.append(_speaker_last_name(sess.papers[pidx]))
                            else:
                                name_cells.append("")
                        while len(name_cells) < n_cols:
                            name_cells.append("")

                        names_row = " & ".join(name_cells)
                        lines.append(f"{t_str} & {names_row} & \\\\ \\hline")

        lines.append(r"\end{tabularx}")
        lines.append(r"\vfill")
        lines.append(r"\end{landscape}")
        lines.append(r"\pagebreak")
        lines.append("")

    return "\n".join(lines)


def _time_to_min(t: str) -> int:
    parts = t.replace(".", ":").split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _fmt_min(m: int) -> str:
    return f"{m // 60}.{m % 60:02d}"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_latex_folder(
    program: Program,
    output_dir: str | Path,
    latex_config: LaTeXConfig | str | Path | None = None,
    papers: list | None = None,
    config_dir: str | Path | None = None,
    abstract_pdf_template: str | None = None,
    presentation_duration_min: int | None = None,
) -> Path:
    """Generate a full LaTeX project folder from *program*.

    Parameters
    ----------
    program : Program
        The fully assigned programme.
    output_dir : str | Path
        Directory to create/populate.
    latex_config : LaTeXConfig | str | Path | None
        Conference metadata. Can be a LaTeXConfig object, a path to a JSON
        file, or None for defaults.
    papers : list | None
        Optional list of Paper objects for generating participants.tex.
    config_dir : str | Path | None
        Directory containing the config files (used to resolve logo path).
    abstract_pdf_template : str | None
        Path template for abstract PDFs, e.g. ``"pdf/conf_<id>.pdf"``.
        When set, ``abstracts.tex`` is generated.
    presentation_duration_min : int | None
        Per-paper presentation duration in minutes.  When provided, it is
        stored in ``latex_config.extra["presentation_duration_min"]`` so
        the generators can use it for exact timing calculations.

    Returns
    -------
    Path
        The output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    # Clean stale .tex files from previous runs
    for old_tex in out.glob("*.tex"):
        old_tex.unlink()

    cfg_dir: Path | None = None
    if latex_config is None:
        lcfg = LaTeXConfig()
    elif isinstance(latex_config, (str, Path)):
        cfg_dir = Path(latex_config).parent
        lcfg = LaTeXConfig.load(latex_config)
    else:
        lcfg = latex_config
    if config_dir is not None:
        cfg_dir = Path(config_dir)

    # Inject presentation_duration_min into extra if provided
    if presentation_duration_min is not None:
        lcfg.extra.setdefault("presentation_duration_min", presentation_duration_min)

    # Determine day file base names (e.g. "day1_tuesday")
    day_file_map: dict[int, str] = {}
    day_files: list[str] = []
    for dp in program.days:
        name = lcfg.day_name(dp.day).lower()
        fname = f"day{dp.day}_{name}"
        day_file_map[dp.day] = fname
        day_files.append(fname)

    # Write commands.tex
    (out / "commands.tex").write_text(_gen_commands(), encoding="utf-8")

    # Write front.tex
    (out / "front.tex").write_text(_gen_front(lcfg), encoding="utf-8")

    # Write program.tex (interleaves plenaries and \input{day_period} files)
    (out / "program.tex").write_text(
        _gen_program_tex(program, lcfg, day_file_map), encoding="utf-8"
    )

    # Write per-period day files
    for dp in program.days:
        n_periods = _count_session_periods(dp)
        for pi in range(n_periods):
            fname = f"{day_file_map[dp.day]}_p{pi}"
            (out / f"{fname}.tex").write_text(
                _gen_day_period_tex(program, dp.day, pi, lcfg), encoding="utf-8"
            )

    # Write participants.tex
    if papers:
        (out / "participants.tex").write_text(
            _gen_participants(papers), encoding="utf-8"
        )
    else:
        # Fallback: extract authors from the programme itself
        all_papers = []
        for dp in program.days:
            for slot in dp.slots:
                for sess in slot.get("sessions", []):
                    if hasattr(sess, 'papers'):
                        all_papers.extend(sess.papers)
        if all_papers:
            (out / "participants.tex").write_text(
                _gen_participants(all_papers), encoding="utf-8"
            )
        else:
            (out / "participants.tex").write_text(
                "%% Participant list — to be filled manually or by a separate script.\n",
                encoding="utf-8",
            )

    # Resolve abstract PDF template from argument or latex_config.extra
    pdf_tpl = abstract_pdf_template or lcfg.extra.get("abstract_pdf_template")

    # Write comments.tex (general info + landscape programme tables)
    (out / "comments.tex").write_text(
        _gen_comments(program, lcfg), encoding="utf-8"
    )

    # Write abstracts.tex (if a PDF template is provided)
    if pdf_tpl:
        (out / "abstracts.tex").write_text(
            _gen_abstracts(program, pdf_tpl), encoding="utf-8"
        )

    # Write main.tex
    (out / "main.tex").write_text(
        _gen_main(
            lcfg, day_files,
            with_comments=True,
            with_abstracts=bool(pdf_tpl),
        ),
        encoding="utf-8",
    )

    # Copy logo if specified — search in config dir, base dir, and data dir
    if lcfg.logo_file:
        logo_name = Path(lcfg.logo_file).name
        candidates = [Path(lcfg.logo_file)]
        if cfg_dir:
            candidates.append(cfg_dir / lcfg.logo_file)
            candidates.append(cfg_dir.parent / lcfg.logo_file)
            candidates.append(cfg_dir.parent / "data" / lcfg.logo_file)
        found = False
        for src in candidates:
            if src.exists():
                shutil.copy2(src, out / logo_name)
                found = True
                break
        if not found:
            logger.warning("Logo file not found (searched %s)", [str(c) for c in candidates])

    logger.info("LaTeX project written to %s", out)
    return out
