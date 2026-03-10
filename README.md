# Conference Programme Manager (CPM)

Generate structured conference programmes from paper submission data, topic preferences, room/chair resources, and scheduling constraints.

## Installation

```bash
pip install conf-program-manager
```

For SBERT-based paper–topic similarity scoring:

```bash
pip install conf-program-manager[similarity]
```

**Development install** (editable, from a local clone):

```bash
git clone https://github.com/johnaoga/cpm.git
cd cpm
pip install -e ".[similarity,dev]"
```

After installation the `cpm` command is available globally.

## Quick Start

A self-contained example is provided in `examples/base/`. Run the full pipeline with:

```bash
cpm generate \
    --config examples/base/config/schedule_config.json \
    --mapping examples/base/config/column_mapping.json \
    --papers  examples/base/data/example_papers.csv \
    --topics  examples/base/data/example_topics.csv \
    --format md --force
```

### Step-by-step usage

```bash
# 1. Generate a skeleton programme
cpm dummy --config config/schedule_config.json

# 2. Manage constraints
cpm constraints --config config/schedule_config.json list
cpm constraints --config config/schedule_config.json add --text "paper_42 = day_1"

# 2b. Interactively review paper comments and add constraints
cpm constraints --config config/schedule_config.json review \
    --mapping config/column_mapping.json --papers data/papers.csv --topics data/topics.csv

# 3. (Optional) Compute SBERT similarity scores
cpm similarity --mapping config/column_mapping.json \
    --papers data/papers.csv --topics data/topics.csv --all

# 4. Assign papers to sessions
cpm papers --config config/schedule_config.json \
    --mapping config/column_mapping.json \
    --papers data/papers.csv --topics data/topics.csv \
    --program output/dummy_program.json

# 5. Assign rooms
cpm rooms --config config/schedule_config.json \
    --program output/program_papers.json \
    --rooms data/rooms.csv --mapping config/column_mapping.json --papers data/papers.csv

# 6. Assign chairs
cpm chairs --config config/schedule_config.json \
    --program output/program_rooms.json \
    --chairs data/chairs.csv --mapping config/column_mapping.json --papers data/papers.csv

# 7. Render output
cpm output --program output/program_chairs.json --format md
cpm output --program output/program_chairs.json --format latex
cpm output --program output/program_chairs.json --format latex-folder \
    --latex-config config/latex_config.json --output output/latex
cpm output --program output/program_chairs.json --format cms-csv

# 8. Manual edits (post-output tweaks)
cpm edit list      --program output/program_chairs.json
cpm edit list-slots --program output/program_chairs.json
cpm edit move-slot  --program output/program_chairs.json --a 1:3 --direction down
cpm edit swap       --program output/program_chairs.json --a S01 --b S05
cpm edit add-slot   --program output/program_chairs.json --day 1 --position 3 \
    --kind break --duration 30 --label "Coffee Break"
cpm edit suggest-chairs --program output/program_chairs.json --a S01 \
    --chairs data/chairs.csv --papers data/papers.csv --mapping config/column_mapping.json
```

## Manual Programme Editing (`edit`)

After the automated pipeline has produced a programme JSON, the `edit` command allows manual adjustments **without re-running** the solver or checking constraints. All actions operate on the programme JSON in-place (or write to `--output`).

```bash
cpm edit <action> --program <programme.json> [options]
```

### Listing

| Action | Description |
|---|---|
| `list` | Show all sessions with day, time, topic, room, chair, and paper count |
| `list-slots` | Show all slots (plenary, break, session, …) with `day:index` refs |

```bash
cpm edit list       --program P.json
cpm edit list-slots --program P.json
```

The `list-slots` output shows a **Ref** column (e.g. `1:3`) that can be used as a slot identifier in other commands.

### Session operations

| Action | Required args | Description |
|---|---|---|
| `swap` | `--a`, `--b` | Swap two sessions (positions + rooms) |
| `move` | `--a`, `--direction` | Move a session up/down to the adjacent SESSION slot |
| `merge` | `--a`, `--b` | Merge `--b` into `--a` (append papers, remove `--b`) |
| `add-session` | `--a`, `--session-id` | Add a new empty session to an existing slot |

```bash
cpm edit swap  --program P.json --a S01 --b S05
cpm edit move  --program P.json --a S01 --direction up
cpm edit merge --program P.json --a S01 --b S02 --output P_edited.json

# Add a session to an existing slot (--a is the slot ref)
cpm edit add-session --program P.json --a 1:4 --session-id S15
cpm edit add-session --program P.json --a 1:4 --session-id S15 --label "Late Posters"
```

### Slot operations

| Action | Required args | Description |
|---|---|---|
| `move-slot` | `--a`, `--direction` | Swap an entire slot with its neighbour (preserves durations and gaps) |
| `add-slot` | `--day`, `--position`, `--kind`, `--duration` | Insert a new slot; subsequent slots shift down |
| `shift-slot` | `--a`, `--minutes` | Shift a slot earlier/later by N minutes; subsequent slots adjust |
| `resize-slot` | `--a`, `--duration` or `--delta` | Change a slot's duration; subsequent slots adjust |

Slots are identified by a **session_id** inside the slot (e.g. `P1_3`, `S01`) or by the **`day:index`** notation shown in `list-slots` (e.g. `1:3`).

```bash
# Swap a slot with its neighbour
cpm edit move-slot --program P.json --a 1:3 --direction down
cpm edit move-slot --program P.json --a S01 --direction up

# Insert a lunch break at position 3 on day 1 (60 min, 15 min gap after)
cpm edit add-slot --program P.json --day 1 --position 3 \
    --kind lunch --duration 60 --label "Lunch"

# Insert a coffee break
cpm edit add-slot --program P.json --day 2 --position 2 \
    --kind break --duration 30 --label "Coffee Break" --gap 10

# Insert a new session slot (auto-creates one empty session)
cpm edit add-slot --program P.json --day 1 --position 5 \
    --kind session --duration 120 --session-id S_Extra

# Insert a plenary
cpm edit add-slot --program P.json --day 1 --position 0 \
    --kind plenary --duration 60 --label "Keynote: Dr. Smith"

# Shift a slot 30 minutes later (subsequent slots follow)
cpm edit shift-slot --program P.json --a 1:4 --minutes 30

# Shift a slot 15 minutes earlier
cpm edit shift-slot --program P.json --a 1:4 --minutes -15

# Extend a slot by 20 minutes
cpm edit resize-slot --program P.json --a 1:4 --delta 20

# Shrink a slot to exactly 90 minutes
cpm edit resize-slot --program P.json --a 1:4 --duration 90

# Resize and recalculate per-paper durations
cpm edit resize-slot --program P.json --a 1:4 --delta -30 --adjust-papers
```

**`move-slot` duration handling**: `move-slot` preserves each slot's intrinsic duration and the gaps between slots. The last slot in a day is normally extended to fill the day-end time; when that slot moves away from the last position its duration is computed as `max_papers × presentation_duration_min`. Use `--presentation-duration` to override the default of 20 minutes.

### Paper operations

| Action | Required args | Description |
|---|---|---|
| `move-paper` | `--paper-id`, `--direction` or `--to-session` | Reorder within session (up/down) or move to another session |
| `swap-papers` | `--paper-id`, `--paper-id-b` | Swap two papers (even across different sessions) |
| `add-paper` | `--paper-id`, `--a` | Add a paper to a session (from CSV or by ID + title) |

```bash
# Reorder within session
cpm edit move-paper --program P.json --paper-id 700 --direction up

# Move paper to a different session
cpm edit move-paper --program P.json --paper-id 700 --to-session S05

# Swap two papers (possibly across sessions)
cpm edit swap-papers --program P.json --paper-id 700 --paper-id-b 800

# Add a paper to a session (loads full data from CSV)
cpm edit add-paper --program P.json --paper-id 999 --a S01 \
    --papers data/papers.csv --mapping config/column_mapping.json

# Add a paper by ID and title only (no CSV needed)
cpm edit add-paper --program P.json --paper-id 999 --a S01 --title "My New Paper"
```

If the paper already exists in the programme, `add-paper` moves it (removes from its current session first).

### Chair operations

| Action | Required args | Description |
|---|---|---|
| `swap-chairs` | `--a`, `--b` | Swap chair assignments between two sessions |
| `replace-chair` | `--a`, `--chair-name` or `--chairs` | Replace a session's chair by name or from suggestions |
| `suggest-chairs` | `--a`, `--chairs` | Show top 10 unassigned chairs ranked by topic affinity |

```bash
# Swap chairs between two sessions
cpm edit swap-chairs --program P.json --a S01 --b S02

# Replace by name substring
cpm edit replace-chair --program P.json --a S01 --chair-name "Doe"

# Interactive: pick from top 10 unassigned chairs
cpm edit replace-chair --program P.json --a S01 \
    --chairs data/chairs.csv --papers data/papers.csv --mapping config/column_mapping.json

# Just view suggestions (no change)
cpm edit suggest-chairs --program P.json --a S01 \
    --chairs data/chairs.csv --papers data/papers.csv --mapping config/column_mapping.json
```

When `--papers` and `--mapping` are provided, chair topic affinity is inferred from paper author data, giving much better ranking. Without them, only pre-existing `topic_ids` from the chairs CSV are used.

### Common `edit` options

| Option | Description |
|---|---|
| `--output FILE` | Write result to FILE instead of overwriting the input |
| `--presentation-duration N` | Minutes per paper for `move-slot` duration calc (default 20) |
| `--to-session ID` | Target session for `move-paper` |
| `--title TEXT` | Paper title for `add-paper` when no CSV is provided |
| `--day N` | Day number for `add-slot` |
| `--position N` | Slot index for `add-slot` (0-based) |
| `--kind TYPE` | Slot kind: `session`, `lunch`, `break`, `plenary`, `dinner` |
| `--duration N` | Duration in minutes for `add-slot` / `resize-slot` |
| `--delta N` | Relative duration change for `resize-slot` (+/−) |
| `--gap N` | Gap in minutes between slots (default 15) |
| `--minutes N` | Shift amount for `shift-slot` (+/−) |
| `--session-id ID` | Session ID for `add-slot` / `add-session` |
| `--label TEXT` | Label for new slots/sessions |
| `--adjust-papers` | Recalculate per-paper durations after `resize-slot` |
| `--papers CSV` | Paper CSV (for `add-paper` or `suggest-chairs` topic inference) |
| `--mapping JSON` | Column-mapping JSON (used with `--papers`) |

## Project Structure

```
cpm/
├── cpm/                          # Python package
│   ├── __init__.py               # Version string
│   ├── cli.py                    # CLI entry point (cpm command)
│   ├── models.py                 # Dataclasses (Paper, Topic, Room, Chair, Session, Program, …)
│   ├── config.py                 # ScheduleConfig: load/save, constraint management
│   ├── data_prep.py              # CSV loading with column mapping and pattern resolution
│   ├── dummy_program.py          # Skeleton programme generation
│   ├── similarity.py             # SBERT paper–topic and topic–topic similarity
│   ├── assign_papers.py          # Paper assignment via OR-Tools CP-SAT (with capacity check)
│   ├── assign_rooms.py           # Room assignment: capacity + topic popularity
│   ├── assign_chairs.py          # Chair assignment: availability, presenter, topic matching
│   ├── edit_program.py           # Manual post-output programme editing operations
│   ├── output.py                 # Markdown, LaTeX, and CMS CSV rendering
│   ├── output_latex.py           # Full LaTeX project folder generation (boa-style)
│   └── output_mobile.py          # Mobile-friendly HTML output
├── examples/
│   └── base/                     # Self-contained example (10 papers, 5 topics)
│       ├── config/               # schedule_config, column_mapping, latex_config
│       └── data/                 # example_papers.csv, example_topics.csv
├── main.py                       # Backward-compat wrapper (delegates to cpm.cli)
├── pyproject.toml                # Package metadata and dependencies
├── requirements.txt
├── LICENSE
└── README.md
```

## Configuration

### Schedule Config (`schedule_config.json`)

| Field | Description |
|---|---|
| `num_days` | Number of conference days |
| `max_session_duration_min` | Maximum session length in minutes |
| `presentation_duration_min` | Per-paper presentation time |
| `num_available_rooms` / `max_rooms_per_day` | Room limits |
| `day_start` / `day_end` | Default daily boundaries (`"HH:MM"`) |
| `first_day_start` / `last_day_end` | Override for first/last day |
| `break_duration_min` | Duration of coffee breaks |
| `morning_break` | `true` to auto-place a morning break |
| `afternoon_break` | `true` to auto-place an afternoon break |
| `lunch_included` | `true` to auto-place a lunch slot |
| `lunch_duration_min` | Duration of lunch |
| `morning_break_target` | Target start time for morning break (default `"10:30"`) |
| `lunch_target` | Target start time for lunch (default `"12:00"`) |
| `afternoon_break_target` | Target start time for afternoon break (default `"15:00"`) |
| `dinner_included`, `dinner_start` | Dinner settings |
| `room_change_penalty_min` | Minutes gap after plenaries/sessions for room changes (default `5`) |
| `day_names` | Day names for session naming, e.g. `["Tuesday", "Wednesday"]` |
| `plenary_slots` | Reserved slots (keynotes, welcome, closing) |
| `constraints` | Scheduling constraints (see [Constraints](#constraints)) |
| `extra` | Free-form dict for additional tunables (see [Extra options](#extra-options)) |

When `morning_break`, `lunch_included`, or `afternoon_break` are `true`, the scheduler places them at (or as close as possible to) the corresponding target time. These targets can be overridden per-conference.

**Session naming**: When `day_names` is set, sessions are named `{Day3}{M|A}{NN}` (e.g. `TueM01`, `WedA03`) using the first 3 letters of the day name, `M`/`A` for morning/afternoon, and a per-period sequence number. Without `day_names`, sessions use `S01`, `S02`, … globally.

**Room change penalty**: After plenary slots (keynotes, etc.) and session blocks, the scheduler inserts a gap of `room_change_penalty_min` minutes before the next session to allow attendees to change rooms. Breaks and lunches already provide natural gaps, so no additional penalty is applied after them.

**Per-day lunch/break overrides**: Explicit constraints like `lunch_1 = 12:30` take priority over the auto-placement heuristic, ensuring lunch is placed at exactly that time.

### Column Mapping (`column_mapping.json`)

Maps CSV columns to paper fields. Supports:
- **Single column**: `"title"`
- **Multiple columns**: `["f_name", "s_name", "t_name"]`
- **Glob patterns**: `"*_mail"` (any column ending with `_mail`)
- **Numbered patterns**: `"author_##"` (e.g. `author_01`, `author_02`, …)

The `encoding` field (default `"utf-8"`) specifies the CSV file encoding. CPM auto-detects encoding: it tries UTF-8 first, then the configured value, then latin-1. If your data contains accented characters (e.g. `é`, `ü`) and you see garbled text, re-run the pipeline — the auto-detection will pick the correct encoding.

### LaTeX Config (`latex_config.json`)

Required when using `--format latex-folder`. Provides conference metadata for the generated LaTeX project:

| Field | Description |
|---|---|
| `conference_title` | Main title (e.g. "International Conference on …") |
| `conference_subtitle` | Subtitle |
| `edition` | Edition string (e.g. "42nd") |
| `date_text` | Date range string (e.g. "March 21 -- 23, 2023") |
| `venue` | Location string |
| `document_title` | "Book of Abstracts" or "Programme" |
| `editors` | Editor names |
| `day_names` | Array of day names (e.g. `["Tuesday", "Wednesday", "Thursday"]`) |
| `day_dates` | Array of day dates (e.g. `["March 21, 2023", …]`) |
| `colors` | RGB color definitions for day/plenary/session headings |

### Constraints

Constraints are listed in the `constraints` array of `schedule_config.json`. They use the syntax `subject op value` and can also be added via CLI or from a text file (one per line, `#` comments).

#### Subject types

| Subject prefix | Meaning | Example |
|---|---|---|
| `paper_<id>` | A paper by its numeric ID | `paper_437` |
| `section_<id>` | A session by its generated ID | `section_S01` |
| `room_<name>` | A room by name | `room_Pinus` |
| `morning_break_<day>` | Morning break time for a specific day | `morning_break_1` |
| `afternoon_break_<day>` | Afternoon break time for a specific day | `afternoon_break_2` |
| `lunch_<day>` | Lunch time for a specific day | `lunch_1` |
| `dinner_<day>` | Dinner time for a specific day | `dinner_3` |

#### Operators

| Operator | Meaning |
|---|---|
| `=` | Must equal (single value) |
| `!=` | Must not equal |
| `<` | Precedence (paper ordering within session) |
| `in` | Must be one of (set) |
| `not_in` | Must not be any of (set) |

#### Value types

| Value | Meaning | Example |
|---|---|---|
| `day_<N>` | Conference day number | `day_1`, `day_3` |
| `S<NN>` | Session ID | `S01`, `S12` |
| `paper_<id>` | Another paper (for same-session / precedence) | `paper_42` |
| `TueM01`, `WedA03` | Session ID (when `day_names` is set) | `TueM01` |
| `HH:MM` | Time value (for break/lunch overrides) | `10:15` |
| `"<text>"` | Label string | `"Welcome"` |
| `{v1, v2, …}` | Set of values | `{day_1, day_2}` |

#### Full examples

```
paper_437 = day_3             # Paper 437 must be on day 3
paper_440 != day_3            # Paper 440 must NOT be on day 3
paper_101 in {day_1, day_2}   # Paper 101 on day 1 or 2
paper_102 = S05               # Paper 102 in session S05
paper_1 = paper_2             # Papers 1 and 2 must be in the same session
paper_1 < paper_2             # Paper 1 must come before paper 2 (same session)
room_Pinus in {day_4, day_5}  # Room Pinus only available days 4–5
section_S01 = "Welcome"       # Section S01 is labelled "Welcome"
morning_break_1 = 10:15       # Day 1 morning break at 10:15
lunch_2 = 12:30               # Day 2 lunch at 12:30
afternoon_break_1 = 15:30     # Day 1 afternoon break at 15:30
```

#### Interactive review

The `review` action interactively walks through papers (prioritising those with comments), displaying the paper ID, title, authors, preferences, and comment. For each paper you can type a constraint or press Enter / `s` to skip, `q` to quit:

```bash
cpm constraints --config config/schedule_config.json review \
    --mapping config/column_mapping.json --papers data/papers.csv --topics data/topics.csv
```

### Extra options

The `extra` dict in `schedule_config.json` provides additional tunables without changing the core schema:

| Key | Type | Default | Description |
|---|---|---|---|
| `topic_diversity` | `bool` | `true` | When enabled, the topic-to-session assignment avoids placing the same topic in parallel sessions of the same time slot, and spreads each topic's sessions across different days. Set to `false` to allow unconstrained topic placement. |

Example:
```json
"extra": {
  "topic_diversity": true
}
```

## Data Files

### Rooms (`rooms.csv`)

Optional CSV file with room names and capacities. Format: `room_name;capacity` (semicolon-separated). If `room_id` column is absent, IDs are auto-generated.

```csv
room_name;capacity
Pinus;40
Salix;120
Fagus;500
```

When room capacity data is provided:
- **Plenary sessions** (keynotes, welcome, etc.) are automatically assigned the **largest** available room.
- **Regular sessions** are ranked by **topic popularity** (number of papers with that topic preference) and matched to rooms by descending capacity — more popular topics get bigger rooms.
- Topic→room continuity is maintained across consecutive time slots.

### Chairs (`chairs.csv`)

Optional CSV file for session chairs. Supports two formats:

**Simple**: `chair_id;chair_name`

**Extended**: `chair_id;lastname;firstname;email;position;arrival;departure`

```csv
chair_id;lastname;firstname;email;position;arrival;departure
4;Doe;Jane;jane.doe@example.com;Professor;1;3
```

When the extended format is used, the assignment logic enforces:
- **Availability**: a chair is only assigned on days between `arrival` and `departure`.
- **No self-chairing**: a chair is never assigned to a session containing one of their own papers.
- **No parallel conflict**: a chair is not assigned if they present a paper in any parallel session of the same time slot.
- **Topic matching**: chairs are preferentially assigned to sessions whose topic matches their own paper topics (inferred by matching chair email/name to paper authors).
- **Load balancing**: among eligible chairs, the least-loaded one is chosen.

## Output Formats

| Format | Flag | Description |
|---|---|---|
| Markdown | `--format md` | Single `.md` file |
| LaTeX | `--format latex` | Single `.tex` file |
| LaTeX folder | `--format latex-folder` | Full LaTeX project (main.tex, commands.tex, front.tex, program.tex, per-period day files, participants.tex). Requires `--latex-config`. |
| Mobile HTML | `--format mobile` | Mobile-responsive HTML page with collapsible sessions, live session tracking, and favourites. |
| CMS CSV | `--format cms-csv` | Two CSV files: `cms_sessions.csv` and `cms_presentations.csv` for import into conference management systems. |

The LaTeX folder output:
- **`program.tex`** interleaves plenary headings and `\input{dayN_period}` files in correct time order.
- **Per-period day files** (`day1_tuesday_p0.tex`, `day2_wednesday_p1.tex`, …) contain session headings and talks for each contiguous session block.
- **`participants.tex`** is auto-generated from paper author data (sorted alphabetically by last name).
- **Logo**: if `logo_file` is set in `latex_config.json`, the file is resolved relative to the config directory (or its parent `data/` folder) and copied into the output.

## Capacity Pre-flight Check

Before paper assignment, the system checks whether total session capacity is sufficient. If not, it displays a diagnostic with suggestions (more rooms, more days, shorter presentations, …) and prompts for confirmation. Use `--force` to skip the prompt.

## SBERT Similarity

- **Paper–Topic scores**: cosine similarity between paper titles and topic names, saved as JSON. Can replace or augment original preferences.
- **Topic–Topic matrix**: identifies similar topics for automatic merging when a topic has few papers. Additionally, this matrix is used during paper assignment as a **fallback scoring mechanism**: when a paper's preferred topics are full, the solver uses topic-topic similarity to find the most related available session, producing a score in the 1–40 range (below direct preference match at 60–100, but well above the baseline of 1). This ensures papers are placed in topically relevant sessions even when their first or second choice is unavailable.

## Publishing

```bash
# Bump version in cpm/__init__.py, then:
pip install build twine
python -m build
twine upload dist/*
```
