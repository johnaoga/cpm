# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] — 2026-11-18
### Changed
- Adding auto publishing to GitHub Releases

## [0.1.1] — 2026-03-09
### Added

#### Manual editing (`cpm edit`)
- **`remove-paper`**: Remove a paper from the programme by `--paper-id`.
- **`rename-room`**: Rename a room across the entire programme by `--room-id` and `--new-name`.
- **`add-chair`**: Assign a chair to a session by `--chair-name`, `--chair-id`, or interactively from `--chairs` CSV.
- **`replace-chair --chair-id`**: Replace a session's chair by numeric chair ID (searches programme first, then `--chairs` CSV).
- **`add-slot --time`**: Insert a slot at an explicit start time (`--time HH:MM`) as an alternative to `--position`.
- **`add-slot --no-adjust`**: Optionally prevent subsequent slots from being adjusted when inserting a new slot.
- **`shift-slot --no-adjust`**: Optionally prevent subsequent slots from being adjusted when shifting a slot.

#### Mobile HTML output
- **`exact_presentation_timing`** support in `program.html`: when enabled in `latex_config.extra`, per-paper durations in the mobile programme use `presentation_duration_min` instead of dividing the session slot evenly.

#### LaTeX generation (`latex_config.extra`)
- **`exact_presentation_timing`** (`bool`): Force each paper to use exactly `presentation_duration_min` minutes instead of spreading the session time evenly.
- **`exact_session_timing`** (`bool`): Set the session heading time range to `presentation_duration_min × num_papers` instead of the full slot duration.
- **`truncate_plenary_title`** (`int`): Auto-truncate plenary titles longer than N characters and append `...` in both `program.tex` and `comments.tex`.
- **`plenary_name`** (`str`): Custom label for plenary headings (default `"Plenary"`).
- **`comment_show_chairs`** (`bool`): Show or hide the chair row in `comments.tex` overview tables (default `true`).
- **`comment_show_breaks`** (`bool`): Show or hide break/lunch/dinner rows in `comments.tex` overview tables (default `true`).
- **`presentation_duration_min`** (`int`): Per-paper duration in minutes used by exact timing options (default `20`); also injectable from `ScheduleConfig` via `generate_latex_folder()`.

### Changed
- `generate_latex_folder()` accepts an optional `presentation_duration_min` parameter so `ScheduleConfig.presentation_duration_min` is forwarded automatically during `cpm generate`.

## [0.1.0] — 2026-02-26

Initial public release with full pipeline: `dummy`, `constraints`, `papers`, `rooms`, `chairs`, `output`, `similarity`, `generate`, and `edit` commands.
