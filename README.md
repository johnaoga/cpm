# Conference Programme Manager (CPM)

Generate structured conference programmes from paper submission data, topic preferences, room/chair resources, and scheduling constraints.

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```bash
# 1. Generate a skeleton programme from schedule config
python main.py dummy --config config/schedule_config.json --output output/dummy_program.json

# 2. Review generated section IDs, then add constraints
python main.py constraints --config config/schedule_config.json add --text "paper_440 = day_1"
python main.py constraints --config config/schedule_config.json list

# 3. (Optional) Compute SBERT similarity scores
python main.py similarity --mapping config/column_mapping.json \
    --papers "data/paper-title and prefs.csv" --topics data/topics.csv --all

# 4. Assign papers to sessions
python main.py papers --config config/schedule_config.json \
    --mapping config/column_mapping.json \
    --papers "data/paper-title and prefs.csv" --topics data/topics.csv \
    --program output/dummy_program.json --output output/program_papers.json

# 5. Assign rooms
python main.py rooms --config config/schedule_config.json \
    --program output/program_papers.json --output output/program_rooms.json

# 6. Assign chairs
python main.py chairs --config config/schedule_config.json \
    --program output/program_rooms.json --output output/program_chairs.json

# 7. Render to Markdown or LaTeX
python main.py output --program output/program_chairs.json --format md --output output/program.md
python main.py output --program output/program_chairs.json --format latex --output output/program.tex

# Or run the full pipeline at once:
python main.py generate --config config/schedule_config.json \
    --mapping config/column_mapping.json \
    --papers "data/paper-title and prefs.csv" --topics data/topics.csv \
    --use-sbert --format md
```

## Project Structure

```
cpm/
├── config/
│   ├── schedule_config.json      # Schedule configuration
│   └── column_mapping.json       # CSV column mapping for paper data
├── cpm/
│   ├── __init__.py
│   ├── models.py                 # Dataclasses: Paper, Topic, Room, Chair, Session, Program, Constraint
│   ├── config.py                 # ScheduleConfig: load/save, constraint management
│   ├── data_prep.py              # CSV loading with column mapping and pattern resolution
│   ├── dummy_program.py          # Skeleton programme generation
│   ├── similarity.py             # SBERT paper–topic and topic–topic similarity
│   ├── assign_papers.py          # Paper assignment via OR-Tools CP-SAT
│   ├── assign_rooms.py           # Room assignment with continuity preference
│   ├── assign_chairs.py          # Chair assignment with round-robin balancing
│   └── output.py                 # Markdown and LaTeX rendering
├── data/
│   ├── paper-title and prefs.csv # Paper submissions
│   └── topics.csv                # Topic list
├── main.py                       # CLI entry point
├── requirements.txt
└── README.md
```

## Configuration

### Schedule Config (`config/schedule_config.json`)

| Field | Description |
|---|---|
| `num_days` | Number of conference days |
| `max_session_duration_min` | Maximum session length in minutes |
| `presentation_duration_min` | Per-paper presentation time |
| `num_available_rooms` / `max_rooms_per_day` | Room limits |
| `day_start` / `day_end` | Default daily boundaries |
| `first_day_start` / `last_day_end` | Override for first/last day |
| `break_duration_min`, `morning_break`, `afternoon_break` | Break settings |
| `lunch_included`, `lunch_duration_min` | Lunch settings |
| `dinner_included`, `dinner_start` | Dinner settings |
| `room_change_penalty_min` | Time penalty for room changes |
| `preliminary_slots` | Reserved slots (keynotes, welcome, closing) |
| `constraints` | Scheduling constraints (see below) |

### Column Mapping (`config/column_mapping.json`)

Maps CSV columns to paper fields. Supports:
- **Single column**: `"title"`
- **Multiple columns**: `["f_name", "s_name", "t_name"]`
- **Glob patterns**: `"*_mail"` (any column ending with `_mail`)
- **Numbered patterns**: `"author_##"` (e.g. `author_01`, `author_02`, …)

### Constraints

Constraints use the syntax `subject op value`:

```
paper_437 = day_3           # Paper 437 must be on day 3
paper_440 != day_3          # Paper 440 must NOT be on day 3
room_Pinus in {day_4, day_5}  # Room Pinus only available days 4–5
section_S01 = "Welcome"     # Section S01 is labelled "Welcome"
```

Constraints can be added from a text file (one per line, `#` comments) or via CLI.

## SBERT Similarity

- **Paper–Topic scores**: cosine similarity between paper titles and topic names, saved as JSON. Can replace or augment original preferences.
- **Topic–Topic matrix**: identifies similar topics for automatic merging when a topic has few papers.
