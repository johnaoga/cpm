# Conference Programme Manager (CPM)

Generate structured conference programmes from paper submission data, topic preferences, room/chair resources, and scheduling constraints.

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

A self-contained example is provided in `examples/base/`. Run the full pipeline with:

```bash
python main.py generate \
    --config examples/base/config/schedule_config.json \
    --mapping examples/base/config/column_mapping.json \
    --papers  examples/base/data/example_papers.csv \
    --topics  examples/base/data/example_topics.csv \
    --format md --force
```

### Step-by-step usage

```bash
# 1. Generate a skeleton programme
python main.py dummy --config config/schedule_config.json

# 2. Manage constraints
python main.py constraints --config config/schedule_config.json list
python main.py constraints --config config/schedule_config.json add --text "paper_42 = day_1"

# 2b. Interactively review paper comments and add constraints
python main.py constraints --config config/schedule_config.json review \
    --mapping config/column_mapping.json --papers data/papers.csv --topics data/topics.csv

# 3. (Optional) Compute SBERT similarity scores
python main.py similarity --mapping config/column_mapping.json \
    --papers data/papers.csv --topics data/topics.csv --all

# 4. Assign papers to sessions
python main.py papers --config config/schedule_config.json \
    --mapping config/column_mapping.json \
    --papers data/papers.csv --topics data/topics.csv \
    --program output/dummy_program.json

# 5. Assign rooms (with optional rooms.csv for capacity-based assignment)
python main.py rooms --config config/schedule_config.json \
    --program output/program_papers.json \
    --rooms data/rooms.csv --mapping config/column_mapping.json --papers data/papers.csv

# 6. Assign chairs (with optional chairs.csv for availability/topic-aware assignment)
python main.py chairs --config config/schedule_config.json \
    --program output/program_rooms.json \
    --chairs data/chairs.csv --mapping config/column_mapping.json --papers data/papers.csv

# 7. Render output
python main.py output --program output/program_chairs.json --format md
python main.py output --program output/program_chairs.json --format latex
python main.py output --program output/program_chairs.json --format latex-folder \
    --latex-config config/latex_config.json --output output/latex
python main.py output --program output/program_chairs.json --format cms-csv
```

## Project Structure

```
cpm/
├── cpm/                          # Python package
│   ├── models.py                 # Dataclasses (Paper, Topic, Room, Chair, Session, Program, …)
│   ├── config.py                 # ScheduleConfig: load/save, constraint management
│   ├── data_prep.py              # CSV loading with column mapping and pattern resolution
│   ├── dummy_program.py          # Skeleton programme generation
│   ├── similarity.py             # SBERT paper–topic and topic–topic similarity
│   ├── assign_papers.py          # Paper assignment via OR-Tools CP-SAT (with capacity check)
│   ├── assign_rooms.py           # Room assignment: capacity + topic popularity
│   ├── assign_chairs.py          # Chair assignment: availability, presenter, topic matching
│   ├── output.py                 # Markdown, LaTeX, and CMS CSV rendering
│   └── output_latex.py           # Full LaTeX project folder generation (boa-style)
├── examples/
│   └── base/                     # Self-contained example (10 papers, 5 topics)
│       ├── config/               # schedule_config, column_mapping, latex_config
│       └── data/                 # example_papers.csv, example_topics.csv
├── main.py                       # CLI entry point
├── run_example.sh                # Run full pipeline for an example folder
├── requirements.txt
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
| `room_change_penalty_min` | Time penalty for room changes |
| `plenary_slots` | Reserved slots (keynotes, welcome, closing) |
| `constraints` | Scheduling constraints (see [Constraints](#constraints)) |
| `extra` | Free-form dict for additional tunables (see [Extra options](#extra-options)) |

When `morning_break`, `lunch_included`, or `afternoon_break` are `true`, the scheduler places them at (or as close as possible to) the corresponding target time. These targets can be overridden per-conference.

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
| `conference_title` | Main title (e.g. "Benelux Meeting") |
| `conference_subtitle` | Subtitle (e.g. "on Systems and Control") |
| `edition` | Edition string (e.g. "42nd") |
| `date_text` | Date range string (e.g. "March 21 -- 23, 2023") |
| `venue` | Location string |
| `document_title` | "Book of Abstracts" or "Programme" |
| `editors` | Editor names |
| `day_names` | Array of day names (e.g. ["Tuesday", "Wednesday", "Thursday"]) |
| `day_dates` | Array of day dates (e.g. ["March 21, 2023", …]) |
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
python main.py constraints --config config/schedule_config.json review \
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
| LaTeX folder | `--format latex-folder` | Full LaTeX project (main.tex, commands.tex, front.tex, dayN.tex, …) matching the Benelux boa style. Requires `--latex-config`. |
| CMS CSV | `--format cms-csv` | Two CSV files: `cms_sessions.csv` and `cms_presentations.csv` for import into conference management systems. |

## Capacity Pre-flight Check

Before paper assignment, the system checks whether total session capacity is sufficient. If not, it displays a diagnostic with suggestions (more rooms, more days, shorter presentations, …) and prompts for confirmation. Use `--force` to skip the prompt.

## SBERT Similarity

- **Paper–Topic scores**: cosine similarity between paper titles and topic names, saved as JSON. Can replace or augment original preferences.
- **Topic–Topic matrix**: identifies similar topics for automatic merging when a topic has few papers. Additionally, this matrix is used during paper assignment as a **fallback scoring mechanism**: when a paper's preferred topics are full, the solver uses topic-topic similarity to find the most related available session, producing a score in the 1–40 range (below direct preference match at 60–100, but well above the baseline of 1). This ensures papers are placed in topically relevant sessions even when their first or second choice is unavailable.
