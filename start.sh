#!/usr/bin/env bash
# Start Shizu. Default: web setup. Use --no-web for terminal setup.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
    echo 'Shizu is not installed yet. Run: bash install.sh' >&2
    exit 1
fi

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    cat <<EOF
Usage: bash start.sh [--no-web]

Starts Shizu.

Options:
  --no-web   terminal setup instead of web setup
  --help     show this help

Examples:
  bash start.sh            # web setup (default)
  bash start.sh --no-web   # terminal setup
EOF
    exit 0
fi

ARGS=()
if [[ "${1:-}" == --no-web ]]; then
    ARGS+=(--no-web)
    shift
fi

exec .venv/bin/python -u -m shizu "${ARGS[@]}" "$@"
