#!/usr/bin/env bash
# Run from a checkout: bash install.sh [--help]
set -Eeuo pipefail
umask 077

if [[ -t 1 ]]; then
    BOLD=$'\e[1m' AMBER=$'\e[38;5;214m' RED=$'\e[31m' DIM=$'\e[2m' RESET=$'\e[0m'
else
    BOLD='' AMBER='' RED='' DIM='' RESET=''
fi
step() { printf '\n%s==>%s %s%s%s\n' "$AMBER" "$RESET" "$BOLD" "$1" "$RESET"; }
die() { printf '%sError:%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }
trap 'printf "\n%sInstallation failed at line %s.%s Fix the error above and run bash install.sh again.\n" "$RED" "$LINENO" "$RESET" >&2' ERR

case "$(uname -s)" in
    Linux|Darwin) ;;
    *) die 'Only Linux and macOS are supported.' ;;
esac

SHIZU_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SHIZU_ROOT"

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    cat <<EOF
Usage: bash install.sh [OPTIONS]

One-command installer for Shizu. Installs Python 3.11-3.14, creates a venv,
installs dependencies, optionally sets up a systemd service, then runs the
Telegram login setup (scripts/install.py).

Common options:
  --auto                  best available tested Python version
  --python 3.X|auto       explicit Python version
  --rebuild --python X    safely rebuild the venv on version X
  --no-start              stop after dependencies (skip login/start)
  --start                 install and start (default)
  --no-web                terminal setup instead of web setup
  --recreate              remove old venv/installer and install fresh
  --root                  allow privileged install actions
  --skip-systemd          do not install systemd unit
  --service-user NAME     run service as existing user
  --create-user NAME      create a new system user for the service
  --yes / -y              answer yes to all prompts
  --dry-run               print actions without executing
  --non-interactive       no prompts at all
EOF
    exit 0
fi

command -v git >/dev/null || die 'git is required. Install it and run the installer again.'
[[ $EUID -eq 0 ]] && { printf '%sWarning:%s running as root. The service will still run non-root by default.\n' "$AMBER" "$RESET" >&2; }

if command -v uv >/dev/null 2>&1; then
    SHIZU_UV="$(command -v uv)"
elif [[ -x "$SHIZU_ROOT/.installer/bin/uv" ]]; then
    SHIZU_UV="$SHIZU_ROOT/.installer/bin/uv"
else
    step 'Downloading uv'
    mkdir -p .installer/bin
    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --silent --show-error https://astral.sh/uv/install.sh -o .installer/uv-install.sh
    elif command -v wget >/dev/null 2>&1; then
        wget -q https://astral.sh/uv/install.sh -O .installer/uv-install.sh
    else
        die 'curl or wget is required to download uv.'
    fi
    UV_UNMANAGED_INSTALL="$SHIZU_ROOT/.installer/bin" sh .installer/uv-install.sh
    SHIZU_UV="$SHIZU_ROOT/.installer/bin/uv"
fi

# Keep managed interpreters and cache local to the project; never touch system Python.
export UV_PYTHON_INSTALL_DIR="$SHIZU_ROOT/.installer/python"
export UV_CACHE_DIR="$SHIZU_ROOT/.installer/cache"

exec python3 "$SHIZU_ROOT/scripts/shizu_installer.py" "$@"
