#!/usr/bin/env bash
# Shizu installer — auto-detects paths, creates dedicated user, supports --root
# Usage: bash install.sh [OPTIONS]
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

# Auto-detect project root from script location
SHIZU_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SHIZU_ROOT"

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    cat <<EOF
Usage: bash install.sh [OPTIONS]

One-command installer for Shizu. Auto-detects project paths, creates
a dedicated system user, installs Python/venv/deps, sets up systemd.

Options:
  --auto                  best available tested Python version
  --python 3.X|auto       explicit Python version
  --rebuild --python X    safely rebuild the venv on version X
  --no-start              stop after dependencies (skip login/start)
  --start                 install and start (default)
  --no-web                terminal setup instead of web setup
  --recreate              remove old venv/installer and install fresh
  --root                  allow running Shizu service as root (not recommended)
  --service-user NAME     run service as existing system user
  --create-user NAME      create new system user (default: shizu)
  --yes / -y              answer yes to all prompts
  --dry-run               print actions without executing
  --skip-systemd          do not install systemd unit
  --non-interactive       no prompts at all

Examples:
  bash install.sh                     # interactive, creates 'shizu' user
  bash install.sh --auto --yes        # fully automatic
  bash install.sh --create-user bot   # create user 'bot'
  bash install.sh --root              # allow root (not recommended)
EOF
    exit 0
fi

command -v git >/dev/null || die 'git is required. Install it and run the installer again.'

# Detect if we're root
IS_ROOT=0
if [[ $EUID -eq 0 ]]; then
    IS_ROOT=1
    printf '%sWarning:%s running as root. ' "$AMBER" "$RESET" >&2
fi

# Parse args to pass to Python installer
ARGS=()
CREATE_USER="shizu"
SERVICE_USER=""
ALLOW_ROOT=0
SKIP_SYSTEMD=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --root) ALLOW_ROOT=1; ARGS+=("$1"); shift ;;
        --create-user) CREATE_USER="$2"; ARGS+=("--create-user" "$2"); shift 2 ;;
        --service-user) SERVICE_USER="$2"; ARGS+=("--service-user" "$2"); shift 2 ;;
        --skip-systemd) SKIP_SYSTEMD=1; ARGS+=("$1"); shift ;;
        --yes|-y) ARGS+=("--yes"); shift ;;
        --dry-run) ARGS+=("--dry-run"); shift ;;
        --non-interactive) ARGS+=("--non-interactive"); shift ;;
        --recreate) ARGS+=("$1"); shift ;;
        --auto) ARGS+=("$1"); shift ;;
        --python) ARGS+=("$1" "$2"); shift 2 ;;
        --rebuild) ARGS+=("$1"); shift ;;
        --no-start) ARGS+=("$1"); shift ;;
        --start) ARGS+=("$1"); shift ;;
        --no-web) ARGS+=("$1"); shift ;;
        *) ARGS+=("$1"); shift ;;
    esac
done

# Bootstrap uv if needed
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

# Keep managed interpreters and cache local to the project
export UV_PYTHON_INSTALL_DIR="$SHIZU_ROOT/.installer/python"
export UV_CACHE_DIR="$SHIZU_ROOT/.installer/cache"

# If root and no --root flag, warn and suggest creating a user
if [[ $IS_ROOT -eq 1 && $ALLOW_ROOT -eq 0 ]]; then
    printf '%sWarning:%s Running as root without --root flag.\n' "$AMBER" "$RESET" >&2
    printf '  The Shizu service will NOT run as root by default.\n' >&2
    printf '  Installer will create a dedicated system user.\n\n' >&2

    if [[ -z "$SERVICE_USER" && -z "${CREATE_USER:-}" ]]; then
        # Auto-create 'shizu' user if interactive
        if [[ -t 0 && -z "${ARGS[*]}" ]]; then
            printf 'Create system user for Shizu service? [Y/n]: ' >&2
            read -r ans || ans="y"
            if [[ "${ans,,}" != "n" ]]; then
                CREATE_USER="shizu"
            fi
        else
            CREATE_USER="shizu"
        fi
        ARGS+=("--create-user" "$CREATE_USER")
    fi
fi

# If not root, run as current user
if [[ $IS_ROOT -eq 0 ]]; then
    # Don't override user choice
    if [[ -z "$SERVICE_USER" && -z "${CREATE_USER:-}" ]]; then
        CURRENT_USER=$(whoami)
        if [[ -t 0 && -z "${ARGS[*]}" ]]; then
            printf 'Run Shizu service as current user "%s"? [Y/n]: ' "$CURRENT_USER" >&2
            read -r ans || ans="y"
            if [[ "${ans,,}" != "n" ]]; then
                ARGS+=("--service-user" "$CURRENT_USER")
            else
                printf 'Enter system username to create for Shizu service: ' >&2
                read -r new_user || new_user="shizu"
                ARGS+=("--create-user" "$new_user")
            fi
        fi
    fi
fi

# Run Python installer with all arguments
exec python3 "$SHIZU_ROOT/scripts/shizu_installer.py" "${ARGS[@]}"