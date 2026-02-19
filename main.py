"""Conference Programme Manager – CLI entry point.

Subcommands
-----------
  dummy       Generate a skeleton programme from schedule config.
  constraints Add / edit / delete / list constraints in the config.
  papers      Assign papers to sessions (OR-Tools CP-SAT).
  rooms       Assign rooms to sessions.
  chairs      Assign chairs to sessions.
  output      Render the programme to Markdown or LaTeX.
  similarity  Compute SBERT paper–topic scores and topic–topic matrix.
  generate    Run the full pipeline (dummy → papers → rooms → chairs → output).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cpm")


# ── helpers ────────────────────────────────────────────────────────────────

def _load_config(path: str):
    from cpm.config import ScheduleConfig
    return ScheduleConfig.load(path)


def _load_mapping(path: str):
    from cpm.data_prep import load_column_mapping
    return load_column_mapping(path)


def _load_program(path: str):
    from cpm.models import Program
    return Program.load(path)


def _ensure_dir(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


# ── sub-command handlers ──────────────────────────────────────────────────

def cmd_dummy(args):
    """Generate a dummy (skeleton) programme."""
    from cpm.config import ScheduleConfig
    from cpm.dummy_program import generate_dummy_program

    cfg = _load_config(args.config)
    prog = generate_dummy_program(cfg)
    _ensure_dir(args.output)
    prog.save(args.output)
    logger.info("Dummy programme saved to %s", args.output)


def cmd_constraints(args):
    """Manage constraints in the schedule config."""
    from cpm.config import ScheduleConfig
    from cpm.data_prep import load_constraint_lines

    cfg = _load_config(args.config)

    if args.action == "list":
        for c in cfg.list_constraints():
            print(f"  [{c.cid}]  {c.to_text()}")
        return

    if args.action == "add":
        if args.file:
            lines = load_constraint_lines(args.file)
            for line in lines:
                c = cfg.add_constraint(line)
                print(f"  Added [{c.cid}]  {c.to_text()}")
        elif args.text:
            c = cfg.add_constraint(args.text)
            print(f"  Added [{c.cid}]  {c.to_text()}")
        else:
            print("Provide --text or --file.", file=sys.stderr)
            return

    elif args.action == "edit":
        if not args.cid or not args.text:
            print("Provide --cid and --text.", file=sys.stderr)
            return
        c = cfg.edit_constraint(args.cid, args.text)
        if c:
            print(f"  Updated [{c.cid}]  {c.to_text()}")
        else:
            print(f"  Constraint {args.cid} not found.", file=sys.stderr)

    elif args.action == "delete":
        if not args.cid:
            print("Provide --cid.", file=sys.stderr)
            return
        if cfg.remove_constraint(args.cid):
            print(f"  Deleted {args.cid}")
        else:
            print(f"  Constraint {args.cid} not found.", file=sys.stderr)

    cfg.save(args.config)
    logger.info("Config updated: %s", args.config)


def _capacity_gate(prog, n_papers, cfg, force: bool = False) -> bool:
    """Run capacity pre-flight check. Returns True if we should proceed."""
    from cpm.assign_papers import check_capacity

    report = check_capacity(prog, n_papers, cfg)
    print("\n── Capacity Pre-flight Check ──")
    print(report.summary())
    print()

    if report.feasible:
        return True

    if force:
        print("--force flag set: proceeding despite insufficient capacity.")
        print(f"  → At most {report.total_capacity}/{report.n_papers} papers will be assigned.\n")
        return True

    answer = input(
        f"Only {report.total_capacity}/{report.n_papers} papers can be assigned.\n"
        "Do you want to proceed anyway? [y/N] "
    ).strip().lower()
    if answer in ("y", "yes"):
        print("  → Proceeding with partial assignment.\n")
        return True

    print("Aborted. Please adjust the schedule config and try again.")
    return False


def cmd_papers(args):
    """Assign papers to sessions."""
    import numpy as np

    from cpm.assign_papers import assign_papers
    from cpm.data_prep import load_papers, load_topics
    from cpm.similarity import load_paper_topic_scores, load_topic_similarity_matrix

    cfg = _load_config(args.config)
    mapping = _load_mapping(args.mapping)
    papers = load_papers(args.papers, mapping)
    topics = load_topics(args.topics)
    prog = _load_program(args.program)

    if not _capacity_gate(prog, len(papers), cfg, force=args.force):
        return

    sbert_scores = None
    if args.sbert_scores:
        sbert_scores = load_paper_topic_scores(args.sbert_scores)

    topic_sim = None
    if args.topic_sim:
        _, _, topic_sim = load_topic_similarity_matrix(args.topic_sim)

    prog = assign_papers(
        prog, papers, topics, cfg,
        sbert_scores=sbert_scores,
        topic_sim_matrix=topic_sim,
        merge_threshold=args.merge_threshold,
        min_group_size=args.min_group_size,
    )
    _ensure_dir(args.output)
    prog.save(args.output)
    logger.info("Papers assigned → %s", args.output)


def cmd_rooms(args):
    """Assign rooms to sessions."""
    from cpm.assign_rooms import assign_rooms
    from cpm.data_prep import generate_default_rooms, load_rooms

    cfg = _load_config(args.config)
    prog = _load_program(args.program)

    if args.rooms and Path(args.rooms).exists():
        rooms = load_rooms(args.rooms)
    else:
        rooms = generate_default_rooms(cfg.num_available_rooms)

    prog = assign_rooms(prog, rooms, cfg)
    _ensure_dir(args.output)
    prog.save(args.output)
    logger.info("Rooms assigned → %s", args.output)


def cmd_chairs(args):
    """Assign chairs to sessions."""
    from cpm.assign_chairs import assign_chairs
    from cpm.data_prep import generate_default_chairs, load_chairs

    cfg = _load_config(args.config)
    prog = _load_program(args.program)

    if args.chairs and Path(args.chairs).exists():
        chairs = load_chairs(args.chairs)
    else:
        chairs = generate_default_chairs(args.num_chairs)

    prog = assign_chairs(prog, chairs, cfg)
    _ensure_dir(args.output)
    prog.save(args.output)
    logger.info("Chairs assigned → %s", args.output)


def cmd_output(args):
    """Render the programme to Markdown or LaTeX."""
    from cpm.output import write_program

    prog = _load_program(args.program)
    _ensure_dir(args.output)
    write_program(prog, args.output, fmt=args.format)
    logger.info("Programme written to %s (%s)", args.output, args.format)


def cmd_similarity(args):
    """Compute SBERT similarity scores."""
    from cpm.data_prep import load_papers, load_topics
    from cpm.similarity import (
        compute_paper_topic_scores,
        compute_topic_similarity_matrix,
        save_paper_topic_scores,
        save_topic_similarity_matrix,
    )

    mapping = _load_mapping(args.mapping)
    papers = load_papers(args.papers, mapping)
    topics = load_topics(args.topics)

    if args.paper_topic or args.all:
        out = args.paper_topic_output or "output/paper_topic_scores.json"
        _ensure_dir(out)
        scores = compute_paper_topic_scores(papers, topics, model_name=args.model)
        save_paper_topic_scores(scores, out)
        logger.info("Paper–topic scores saved to %s", out)

    if args.topic_topic or args.all:
        out = args.topic_topic_output or "output/topic_similarity_matrix.json"
        _ensure_dir(out)
        matrix = compute_topic_similarity_matrix(topics, model_name=args.model)
        save_topic_similarity_matrix(matrix, topics, out)
        logger.info("Topic–topic similarity saved to %s", out)


def cmd_generate(args):
    """Full pipeline: dummy → papers → rooms → chairs → output."""
    import numpy as np

    from cpm.assign_chairs import assign_chairs
    from cpm.assign_papers import assign_papers
    from cpm.assign_rooms import assign_rooms
    from cpm.config import ScheduleConfig
    from cpm.data_prep import (
        generate_default_chairs,
        generate_default_rooms,
        load_chairs,
        load_papers,
        load_rooms,
        load_topics,
    )
    from cpm.dummy_program import generate_dummy_program
    from cpm.output import write_program
    from cpm.similarity import (
        compute_paper_topic_scores,
        compute_topic_similarity_matrix,
        load_paper_topic_scores,
        load_topic_similarity_matrix,
        save_paper_topic_scores,
        save_topic_similarity_matrix,
    )

    cfg = _load_config(args.config)
    mapping = _load_mapping(args.mapping)
    papers = load_papers(args.papers, mapping)
    topics = load_topics(args.topics)

    # Step 1 – dummy programme
    logger.info("Step 1/6: generating dummy programme …")
    prog = generate_dummy_program(cfg)

    # Step 2 – SBERT scores (optional)
    sbert_scores = None
    topic_sim = None
    if args.use_sbert:
        logger.info("Step 2/6: computing SBERT scores …")
        sbert_out = args.sbert_scores or "output/paper_topic_scores.json"
        topic_sim_out = args.topic_sim or "output/topic_similarity_matrix.json"
        _ensure_dir(sbert_out)
        _ensure_dir(topic_sim_out)

        if Path(sbert_out).exists():
            sbert_scores = load_paper_topic_scores(sbert_out)
        else:
            sbert_scores = compute_paper_topic_scores(
                papers, topics, model_name=args.model,
            )
            save_paper_topic_scores(sbert_scores, sbert_out)

        if Path(topic_sim_out).exists():
            _, _, topic_sim = load_topic_similarity_matrix(topic_sim_out)
        else:
            topic_sim = compute_topic_similarity_matrix(
                topics, model_name=args.model,
            )
            save_topic_similarity_matrix(topic_sim, topics, topic_sim_out)
    else:
        logger.info("Step 2/6: skipping SBERT (--use-sbert not set)")

    # Step 3 – capacity check + assign papers
    if not _capacity_gate(prog, len(papers), cfg, force=args.force):
        return

    logger.info("Step 3/6: assigning papers …")
    prog = assign_papers(
        prog, papers, topics, cfg,
        sbert_scores=sbert_scores,
        topic_sim_matrix=topic_sim,
    )

    # Step 4 – assign rooms
    logger.info("Step 4/6: assigning rooms …")
    if args.rooms and Path(args.rooms).exists():
        rooms = load_rooms(args.rooms)
    else:
        rooms = generate_default_rooms(cfg.num_available_rooms)
    prog = assign_rooms(prog, rooms, cfg)

    # Step 5 – assign chairs
    logger.info("Step 5/6: assigning chairs …")
    if args.chairs and Path(args.chairs).exists():
        chairs = load_chairs(args.chairs)
    else:
        chairs = generate_default_chairs(args.num_chairs)
    prog = assign_chairs(prog, chairs, cfg)

    # Step 6 – output
    logger.info("Step 6/6: writing output …")
    prog_out = args.output or "output/program.json"
    _ensure_dir(prog_out)
    prog.save(prog_out)

    fmt = args.format or "md"
    render_out = str(Path(prog_out).with_suffix(f".{fmt}"))
    write_program(prog, render_out, fmt=fmt)

    logger.info("Done. Programme → %s, Rendered → %s", prog_out, render_out)


# ── argument parser ──────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cpm",
        description="Conference Programme Manager",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # ---- dummy ----
    sp = sub.add_parser("dummy", help="Generate a skeleton programme")
    sp.add_argument("--config", required=True, help="Schedule config JSON")
    sp.add_argument("--output", default="output/dummy_program.json")
    sp.set_defaults(func=cmd_dummy)

    # ---- constraints ----
    sp = sub.add_parser("constraints", help="Manage constraints")
    sp.add_argument("--config", required=True, help="Schedule config JSON")
    sp.add_argument("action", choices=["list", "add", "edit", "delete"])
    sp.add_argument("--text", help="Constraint text (for add/edit)")
    sp.add_argument("--cid", help="Constraint ID (for edit/delete)")
    sp.add_argument("--file", help="Text file with constraints (for add)")
    sp.set_defaults(func=cmd_constraints)

    # ---- papers ----
    sp = sub.add_parser("papers", help="Assign papers to sessions")
    sp.add_argument("--config", required=True)
    sp.add_argument("--mapping", required=True, help="Column-mapping JSON")
    sp.add_argument("--papers", required=True, help="Paper CSV")
    sp.add_argument("--topics", required=True, help="Topics CSV")
    sp.add_argument("--program", required=True, help="Input programme JSON (dummy)")
    sp.add_argument("--output", default="output/program_papers.json")
    sp.add_argument("--sbert-scores", help="Pre-computed SBERT scores JSON")
    sp.add_argument("--topic-sim", help="Pre-computed topic similarity JSON")
    sp.add_argument("--merge-threshold", type=float, default=0.75)
    sp.add_argument("--min-group-size", type=int, default=3)
    sp.add_argument("--force", action="store_true",
                    help="Proceed even if capacity is insufficient")
    sp.set_defaults(func=cmd_papers)

    # ---- rooms ----
    sp = sub.add_parser("rooms", help="Assign rooms to sessions")
    sp.add_argument("--config", required=True)
    sp.add_argument("--program", required=True, help="Input programme JSON")
    sp.add_argument("--rooms", help="Rooms CSV (optional, generates defaults)")
    sp.add_argument("--output", default="output/program_rooms.json")
    sp.set_defaults(func=cmd_rooms)

    # ---- chairs ----
    sp = sub.add_parser("chairs", help="Assign chairs to sessions")
    sp.add_argument("--config", required=True)
    sp.add_argument("--program", required=True, help="Input programme JSON")
    sp.add_argument("--chairs", help="Chairs CSV (optional, generates defaults)")
    sp.add_argument("--num-chairs", type=int, default=10)
    sp.add_argument("--output", default="output/program_chairs.json")
    sp.set_defaults(func=cmd_chairs)

    # ---- output ----
    sp = sub.add_parser("output", help="Render programme to md/latex")
    sp.add_argument("--program", required=True)
    sp.add_argument("--format", choices=["md", "latex"], default="md")
    sp.add_argument("--output", default="output/program.md")
    sp.set_defaults(func=cmd_output)

    # ---- similarity ----
    sp = sub.add_parser("similarity", help="Compute SBERT similarity scores")
    sp.add_argument("--mapping", required=True)
    sp.add_argument("--papers", required=True)
    sp.add_argument("--topics", required=True)
    sp.add_argument("--model", default="all-MiniLM-L6-v2")
    sp.add_argument("--paper-topic", action="store_true")
    sp.add_argument("--topic-topic", action="store_true")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--paper-topic-output", default="output/paper_topic_scores.json")
    sp.add_argument("--topic-topic-output", default="output/topic_similarity_matrix.json")
    sp.set_defaults(func=cmd_similarity)

    # ---- generate (full pipeline) ----
    sp = sub.add_parser("generate", help="Full pipeline")
    sp.add_argument("--config", required=True)
    sp.add_argument("--mapping", required=True)
    sp.add_argument("--papers", required=True)
    sp.add_argument("--topics", required=True)
    sp.add_argument("--rooms", help="Rooms CSV (optional)")
    sp.add_argument("--chairs", help="Chairs CSV (optional)")
    sp.add_argument("--num-chairs", type=int, default=10)
    sp.add_argument("--output", default="output/program.json")
    sp.add_argument("--format", choices=["md", "latex"], default="md")
    sp.add_argument("--use-sbert", action="store_true")
    sp.add_argument("--model", default="all-MiniLM-L6-v2")
    sp.add_argument("--sbert-scores", help="Pre-computed SBERT scores JSON")
    sp.add_argument("--topic-sim", help="Pre-computed topic similarity JSON")
    sp.add_argument("--force", action="store_true",
                    help="Proceed even if capacity is insufficient")
    sp.set_defaults(func=cmd_generate)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
