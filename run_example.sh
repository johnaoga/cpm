#!/usr/bin/env bash
#
# Run the full CPM pipeline for a given example folder.
#
# Usage:
#   ./run_example.sh <base_folder>
#
# Example:
#   ./run_example.sh examples/base
#   ./run_example.sh examples/benelux
#
# The base folder must contain:
#   config/schedule_config.json
#   config/column_mapping.json
#   config/latex_config.json   (optional, for latex-folder output)
#   data/<papers>.csv
#   data/<topics>.csv
#
# Output will be written to <base_folder>/output/

set -euo pipefail

# Auto-detect Python: prefer local venv, then python3, then python
if [ -x "venv/bin/python" ]; then
  PYTHON="venv/bin/python"
elif command -v python3 &>/dev/null; then
  PYTHON="python3"
else
  PYTHON="python"
fi

BASE="${1:?Usage: $0 <base_folder>}"

# Resolve paths
CONFIG="$BASE/config/schedule_config.json"
MAPPING="$BASE/config/column_mapping.json"
LATEX_CFG="$BASE/config/latex_config.json"
OUTPUT_DIR="$BASE/output"

# Auto-detect data files
PAPERS=$(find "$BASE/data" -name '*.csv' ! -name '*topic*' ! -name '*room*' ! -name '*chair*' | head -1)
TOPICS=$(find "$BASE/data" -name '*topic*' -name '*.csv' | head -1)
ROOMS_CSV=$(find "$BASE/data" -name '*room*' -name '*.csv' 2>/dev/null | head -1)
CHAIRS_CSV=$(find "$BASE/data" -name '*chair*' -name '*.csv' 2>/dev/null | head -1)

if [ -z "$PAPERS" ] || [ -z "$TOPICS" ]; then
  echo "ERROR: Could not find papers and/or topics CSV in $BASE/data/"
  exit 1
fi

echo "========================================"
echo " CPM Pipeline — $BASE"
echo "========================================"
echo " Config  : $CONFIG"
echo " Mapping : $MAPPING"
echo " Papers  : $PAPERS"
echo " Topics  : $TOPICS"
echo " Rooms   : ${ROOMS_CSV:-(default)}"
echo " Chairs  : ${CHAIRS_CSV:-(default)}"
echo " Output  : $OUTPUT_DIR"
echo "========================================"
echo ""

mkdir -p "$OUTPUT_DIR"

# ── Step 1: Dummy programme ──
echo "▶ Step 1/7: Generating dummy programme …"
$PYTHON main.py dummy \
  --config "$CONFIG" \
  --output "$OUTPUT_DIR/dummy_program.json"
echo ""

# ── Step 2: Assign papers ──
echo "▶ Step 2/7: Assigning papers …"
$PYTHON main.py papers \
  --config "$CONFIG" \
  --mapping "$MAPPING" \
  --papers "$PAPERS" \
  --topics "$TOPICS" \
  --program "$OUTPUT_DIR/dummy_program.json" \
  --output "$OUTPUT_DIR/program_papers.json" \
  --force
echo ""

# ── Step 3: Assign rooms ──
echo "▶ Step 3/7: Assigning rooms …"
ROOMS_ARGS=""
if [ -n "$ROOMS_CSV" ]; then
  ROOMS_ARGS="--rooms $ROOMS_CSV"
fi
$PYTHON main.py rooms \
  --config "$CONFIG" \
  --program "$OUTPUT_DIR/program_papers.json" \
  --mapping "$MAPPING" --papers "$PAPERS" \
  $ROOMS_ARGS \
  --output "$OUTPUT_DIR/program_rooms.json"
echo ""

# ── Step 4: Assign chairs ──
echo "▶ Step 4/7: Assigning chairs …"
CHAIRS_ARGS=""
if [ -n "$CHAIRS_CSV" ]; then
  CHAIRS_ARGS="--chairs $CHAIRS_CSV"
fi
$PYTHON main.py chairs \
  --config "$CONFIG" \
  --program "$OUTPUT_DIR/program_rooms.json" \
  --mapping "$MAPPING" --papers "$PAPERS" \
  $CHAIRS_ARGS \
  --output "$OUTPUT_DIR/program_chairs.json"
echo ""

# ── Step 5: Output Markdown ──
echo "▶ Step 5/7: Rendering Markdown …"
$PYTHON main.py output \
  --program "$OUTPUT_DIR/program_chairs.json" \
  --format md \
  --output "$OUTPUT_DIR/program.md"
echo ""

# ── Step 6: Output LaTeX folder ──
if [ -f "$LATEX_CFG" ]; then
  echo "▶ Step 6/7: Generating LaTeX folder …"
  $PYTHON main.py output \
    --program "$OUTPUT_DIR/program_chairs.json" \
    --format latex-folder \
    --latex-config "$LATEX_CFG" \
    --output "$OUTPUT_DIR/latex"
  echo ""
else
  echo "▶ Step 6/7: Skipping LaTeX folder (no $LATEX_CFG found)"
  echo ""
fi

# ── Step 7: Output CMS CSV ──
echo "▶ Step 7/7: Generating CMS CSV files …"
$PYTHON main.py output \
  --program "$OUTPUT_DIR/program_chairs.json" \
  --format cms-csv \
  --cms-sessions "$OUTPUT_DIR/cms_sessions.csv" \
  --cms-presentations "$OUTPUT_DIR/cms_presentations.csv"
echo ""

echo "========================================"
echo " Done! Output files in $OUTPUT_DIR:"
ls -1 "$OUTPUT_DIR"
if [ -d "$OUTPUT_DIR/latex" ]; then
  echo ""
  echo " LaTeX folder:"
  ls -1 "$OUTPUT_DIR/latex"
fi
echo "========================================"
