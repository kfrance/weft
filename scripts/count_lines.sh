#!/bin/bash
# Lines of Code Counter for weft project
# Excludes: .venv, .git, build, __pycache__, .weft, cache directories

set -e

EXCLUDE_PATHS=(
    '*/.venv/*'
    '*/.git/*'
    '*/build/*'
    '*/__pycache__/*'
    '*/.weft/*'
    '*/.uv-cache/*'
    '*/.pytest_cache/*'
    '*/src/*.egg-info/*'
    './uv.lock'
)

# Build find command exclude arguments
EXCLUDE_ARGS=""
for pattern in "${EXCLUDE_PATHS[@]}"; do
    EXCLUDE_ARGS="$EXCLUDE_ARGS -not -path '$pattern'"
done

echo "=========================================="
echo "  Lines of Code Report"
echo "=========================================="
echo ""

# Count non-test lines
echo "NON-TEST LINES:"
eval "find . -type f $EXCLUDE_ARGS -not -path '*/tests/*' -not -name '*.pyc'" | xargs wc -l 2>/dev/null | tail -1
echo ""

# Count test lines
echo "TEST LINES:"
eval "find . -type f $EXCLUDE_ARGS -path '*/tests/*' -not -name '*.pyc'" | xargs wc -l 2>/dev/null | tail -1
echo ""

# Total lines
echo "TOTAL PROJECT LINES:"
eval "find . -type f $EXCLUDE_ARGS -not -name '*.pyc'" | xargs wc -l 2>/dev/null | tail -1
echo ""

# Python
echo "Python (.py):"
eval "find . -type f -name '*.py' $EXCLUDE_ARGS" | xargs wc -l 2>/dev/null | tail -1
echo ""

# Markdown
echo "Markdown (.md):"
eval "find . -type f -name '*.md' $EXCLUDE_ARGS" | xargs wc -l 2>/dev/null | tail -1
echo ""

# JSON
echo "JSON (.json):"
eval "find . -type f -name '*.json' $EXCLUDE_ARGS" | xargs wc -l 2>/dev/null | tail -1
echo ""

# Shell scripts
echo "Shell scripts (.sh):"
eval "find . -type f -name '*.sh' $EXCLUDE_ARGS" | xargs wc -l 2>/dev/null | tail -1
echo ""

echo "=========================================="
echo "  'Other' Files Breakdown"
echo "=========================================="
echo ""

# List "other" files with line counts
echo "Sample of other files (first 20):"
eval "find . -type f $EXCLUDE_ARGS \
    -not -name '*.py' \
    -not -name '*.md' \
    -not -name '*.json' \
    -not -name '*.sh' \
    -not -name '*.pyc'" | head -20 | while read file; do
    lines=$(wc -l < "$file" 2>/dev/null || echo "0")
    echo "  $lines lines: $file"
done
echo ""

# Count of other files by extension
echo "Other files grouped by extension:"
eval "find . -type f $EXCLUDE_ARGS \
    -not -name '*.py' \
    -not -name '*.md' \
    -not -name '*.json' \
    -not -name '*.sh' \
    -not -name '*.pyc'" | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
echo ""

echo "=========================================="
