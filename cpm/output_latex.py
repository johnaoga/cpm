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
from .models import Program, Session, SlotKind, TimeSlot

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


def _gen_main(lcfg: LaTeXConfig, day_files: list[str]) -> str:
    """Generate main.tex (master document)."""
    header_left = _esc(lcfg.header_left or f"{lcfg.edition} {lcfg.conference_title}")
    header_right = _esc(lcfg.header_right)
    pdf_title = f"{lcfg.document_title} {lcfg.edition} {lcfg.conference_title}"

    col = lcfg.colors
    daybox = col.get("daybox", "1,.2,.2")
    plebox = col.get("plebox", ".4,0,.8")
    sesbox = col.get("sesbox", ".8,.8,1")

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

\\nopagebreak \\vfill

%% -- PARTICIPANTS -- %%
\\onecolumn \\cleardoublepage \\mbox{{}} \\vspace*{{6cm}}
\\begin{{center}}
\\Huge\\textbf{{Part 2\\\\[2ex] List of Participants}}
\\end{{center}}
\\hypertarget{{P:4}}{{}} \\label{{P:4}} \\twocolumn \\cleardoublepage

\\input{{participants}}
\\nopagebreak \\vfill

\\end{{document}}
"""


def _gen_program_tex(program: Program, lcfg: LaTeXConfig, day_file_map: dict[int, str]) -> str:
    """Generate program.tex — the programmatic table of contents."""
    lines: list[str] = []

    for day_prog in program.days:
        day_num = day_prog.day
        heading = lcfg.full_day_heading(day_num)
        lines.append(f"\\dayheading{{{_esc(heading)}}}")
        lines.append("")
        lines.append("\\medskip\\nopagebreak")
        lines.append("")

        for slot in day_prog.slots:
            ts: TimeSlot = slot["time_slot"]

            if ts.kind == SlotKind.PLENARY:
                lines.append(
                    f"\\pleheading{{Plenary}}{{}}"
                    f"{{{_esc(ts.label)}}}{{}}"
                    f"{{}}{{{ts.start}--{ts.end}}}"
                )
                lines.append("")
                lines.append("\\medskip\\nopagebreak")
                lines.append("")
                continue

            if ts.kind in (SlotKind.BREAK, SlotKind.LUNCH, SlotKind.DINNER):
                continue

        # Input the day file from program.tex
        if day_num in day_file_map:
            lines.append(f"\\input{{{day_file_map[day_num]}}}")
            lines.append("")

    return "\n".join(lines)


def _gen_day_tex(program: Program, day_num: int, lcfg: LaTeXConfig) -> str:
    """Generate a dayN.tex file with sessions and talks for one day."""
    lines: list[str] = []
    lines.append(f"%% THIS IS THE PROGRAM DATA FOR DAY {day_num}")
    lines.append("%% AUTOMATICALLY GENERATED BY CPM")
    lines.append("")

    day_prog = None
    for dp in program.days:
        if dp.day == day_num:
            day_prog = dp
            break
    if day_prog is None:
        return "\n".join(lines)

    for slot in day_prog.slots:
        ts: TimeSlot = slot["time_slot"]
        sessions: list[Session] = slot["sessions"]

        if ts.kind != SlotKind.SESSION:
            continue

        for sess in sessions:
            room_name = sess.room.name if sess.room else ""
            topic_name = sess.topic.name if sess.topic else ""
            chair_name = sess.chair.name if sess.chair else ""
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

            pres_dur = 20  # default
            try:
                if len(sess.papers) > 0 and ts.duration_minutes > 0:
                    pres_dur = ts.duration_minutes // len(sess.papers)
            except Exception:
                pass

            for idx, paper in enumerate(sess.papers):
                # Compute presentation time
                start_min = _time_to_min(ts.start) + idx * pres_dur
                end_min = start_min + pres_dur
                talk_start = _fmt_min(start_min)
                talk_end = _fmt_min(end_min)
                talk_id = f"{sess.session_id}-{idx + 1}"

                # Authors: up to 3 pairs (name, affiliation), then last author as speaker
                authors = paper.authors
                a1_name = _esc(authors[0].name) if len(authors) > 0 else ""
                a1_aff = _esc(authors[0].affiliation) if len(authors) > 0 and authors[0].affiliation else ""
                a2_name = _esc(authors[1].name) if len(authors) > 1 else ""
                a2_aff = _esc(authors[1].affiliation) if len(authors) > 1 and authors[1].affiliation else ""
                a3_name = _esc(authors[2].name) if len(authors) > 2 else ""
                a3_aff = _esc(authors[2].affiliation) if len(authors) > 2 and authors[2].affiliation else ""
                # Last arg: speaker name (use first author)
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

    Returns
    -------
    Path
        The output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if latex_config is None:
        lcfg = LaTeXConfig()
    elif isinstance(latex_config, (str, Path)):
        lcfg = LaTeXConfig.load(latex_config)
    else:
        lcfg = latex_config

    # Determine day file names
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

    # Write program.tex
    (out / "program.tex").write_text(
        _gen_program_tex(program, lcfg, day_file_map), encoding="utf-8"
    )

    # Write day files
    for dp in program.days:
        fname = day_file_map[dp.day]
        (out / f"{fname}.tex").write_text(
            _gen_day_tex(program, dp.day, lcfg), encoding="utf-8"
        )

    # Write participants.tex (placeholder)
    (out / "participants.tex").write_text(
        "%% Participant list — to be filled manually or by a separate script.\n",
        encoding="utf-8",
    )

    # Write main.tex
    (out / "main.tex").write_text(
        _gen_main(lcfg, day_files), encoding="utf-8"
    )

    # Copy logo if specified and exists
    if lcfg.logo_file:
        src = Path(lcfg.logo_file)
        if src.exists():
            shutil.copy2(src, out / src.name)

    logger.info("LaTeX project written to %s", out)
    return out
