#!/usr/bin/env bash
# Shizu Installer — Step-by-step interactive setup
set -Eeuo pipefail
umask 077

# Colors
if [[ -t 1 ]]; then
    BOLD=$'\e[1m' AMBER=$'\e[38;5;214m' RED=$'\e[31m' GREEN=$'\e[32m' CYAN=$'\e[36m' DIM=$'\e[2m' RESET=$'\e[0m'
else
    BOLD='' AMBER='' RED='' GREEN='' CYAN='' DIM='' RESET=''
fi

step() { printf '\n%s==>%s %s%s%s\n' "$AMBER" "$RESET" "$BOLD" "$1" "$RESET"; }
info() { printf '%s%s%s\n' "$CYAN" "$1" "$RESET"; }
ok() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$1"; }
die() { printf '%sError:%s %s\n' "$RED" "$RESET" "$1" >&2; exit 1; }
warn() { printf '%sWarning:%s %s\n' "$AMBER" "$RESET" "$1" >&2; }

trap 'printf "\n%sInstallation failed at line %s.%s Fix the error above and run bash install.sh again.\n" "$RED" "$LINENO" "$RESET" >&2' ERR

case "$(uname -s)" in
    Linux|Darwin) ;;
    *) die 'Only Linux and macOS are supported.' ;;
esac

# Auto-detect project root
SHIZU_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SHIZU_ROOT"

# Handle --help early
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    cat <<EOF
Usage: bash install.sh [OPTIONS]

Step-by-step interactive installer for Shizu.

Options:
  --help, -h     Show this help
  --reinstall    Reinstall without resetting Telegram session
  --remove       Fully remove everything
  --run          Just run Shizu
  --update       Check for GitHub updates (current branch)

Without options: runs interactive step-by-step installer.
EOF
    exit 0
fi

# State file for tracking installation progress
STATE_FILE="$SHIZU_ROOT/.installer/state.json"
mkdir -p "$SHIZU_ROOT/.installer"

# Generate random service suffix
generate_service_suffix() {
    cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 5 | head -n 1
}

# Get or create service name
get_service_name() {
    local state
    state=$(load_state)
    if echo "$state" | grep -q "service_name="; then
        echo "$state" | grep "service_name=" | cut -d= -f2
    else
        local suffix
        suffix=$(generate_service_suffix)
        local service_name="shizu_${suffix}.service"
        save_state "{\"service_name\":\"$service_name\"}"
        echo "$service_name"
    fi
}

# Handle command-line options
case "${1:-}" in
    --reinstall) REINSTALL=1; shift ;;
    --remove) FULL_REMOVE=1; shift ;;
    --run) SKIP_INSTALL=1; shift ;;
    --update) CHECK_UPDATE=1; shift ;;
esac

# Load previous state
load_state() {
    if [[ -f "$STATE_FILE" ]]; then
        python3 -c "
import json, sys, os
state_file = sys.argv[1]
try:
    with open(state_file) as f:
        data = json.load(f)
    for k, v in data.items():
        print(f'{k}={v}')
except:
    pass
" "$STATE_FILE"
    fi
}

save_state() {
    python3 -c "
import json, sys, os
data = {}
if os.path.exists('$STATE_FILE'):
    try:
        with open('$STATE_FILE') as f:
            data = json.load(f)
    except:
        pass
data.update($1)
with open('$STATE_FILE', 'w') as f:
    json.dump(data, f, indent=2)
"
}

# Check if already installed
check_existing() {
    local state
    state=$(load_state)
    if [[ -n "$state" ]] && [[ -z "${REINSTALL:-}" ]] && [[ -z "${FULL_REMOVE:-}" ]] && [[ -z "${SKIP_INSTALL:-}" ]] && [[ -z "${CHECK_UPDATE:-}" ]]; then
        return 0
    fi
    return 1
}

# Show main menu for existing installation
show_main_menu() {
    local service_name
    service_name=$(get_service_name)
    step "Shizu уже установлен. Что сделать?"
    echo "  1) Переустановить (без сброса сессии Telegram)"
    echo "  2) Удалить всё (но сохранить сессию Telegram)"
    echo "  3) Удалить всё (удаляет всё кроме исходного кода)"
    echo "  4) Пропустить установку и просто запустить"
    echo "  5) Проверить обновления с GitHub (текущая ветка)"
    echo "  6) Показать имя системного сервиса ($service_name)"
    echo "  7) Выход"
    while true; do
        read -rp "Выбор [1-7]: " choice
        case "$choice" in
            1) REINSTALL=1; return 0 ;;
            2) FULL_REMOVE_KEEP_SESSION=1; return 0 ;;
            3) FULL_REMOVE_ALL=1; return 0 ;;
            4) SKIP_INSTALL=1; return 0 ;;
            5) CHECK_UPDATE=1; return 0 ;;
            6) echo "Сервис: $service_name"; echo "Команды: systemctl status $service_name, journalctl -u $service_name -f"; continue ;;
            7) exit 0 ;;
            *) echo "Неверный выбор" ;;
        esac
    done
}

# Stage 1: Choose user
stage_user() {
    step "Этап 1/5: Выбор пользователя для запуска сервиса"
    echo "  1) root (не рекомендуется)"
    echo "  2) Текущий пользователь ($USER)"
    echo "  3) Создать нового системного пользователя"
    while true; do
        read -rp "Выбор [1-3]: " choice
        case "$choice" in
            1) SERVICE_USER_MODE="root"; SERVICE_USER="root"; break ;;
            2) SERVICE_USER_MODE="current"; SERVICE_USER="$USER"; break ;;
            3) SERVICE_USER_MODE="create"
               read -rp "Имя нового пользователя: " newuser
               [[ -n "$newuser" ]] || { echo "Имя не может быть пустым"; continue; }
               SERVICE_USER="$newuser"
               break ;;
            *) echo "Неверный выбор" ;;
        esac
    done
    save_state "{\"service_user_mode\":\"$SERVICE_USER_MODE\",\"service_user\":\"$SERVICE_USER\"}"
    ok "Пользователь: $SERVICE_USER (режим: $SERVICE_USER_MODE)"
}

# Stage 2: Choose Python version
stage_python() {
    step "Этап 2/5: Выбор версии Python"
    # Detect available versions
    local available=()
    for v in 3.14 3.13 3.12 3.11; do
        if command -v "python$v" >/dev/null 2>&1; then
            available+=("$v")
        fi
    done
    
    echo "  1) Авто — самая новая доступная (по умолчанию: ${available[0]:-3.14})"
    echo "  2) Python 3.14"
    echo "  3) Python 3.13"
    echo "  4) Python 3.12"
    echo "  5) Python 3.11"
    while true; do
        read -rp "Выбор [1-5]: " choice
        case "$choice" in
            1) PYTHON_VER="auto"; break ;;
            2) PYTHON_VER="3.14"; break ;;
            3) PYTHON_VER="3.13"; break ;;
            4) PYTHON_VER="3.12"; break ;;
            5) PYTHON_VER="3.11"; break ;;
            *) echo "Неверный выбор" ;;
        esac
    done
    save_state "{\"python_version\":\"$PYTHON_VER\"}"
    ok "Python: $PYTHON_VER"
}

# Stage 3: Web or terminal
stage_interface() {
    step "Этап 3/5: Способ регистрации в Telegram"
    echo "  1) Веб-интерфейс (через браузер)"
    echo "  2) Терминал (QR-код / код / 2FA)"
    while true; do
        read -rp "Выбор [1-2]: " choice
        case "$choice" in
            1) INTERFACE_MODE="web"; break ;;
            2) INTERFACE_MODE="terminal"; break ;;
            *) echo "Неверный выбор" ;;
        esac
    done
    save_state "{\"interface_mode\":\"$INTERFACE_MODE\"}"
    ok "Режим: $INTERFACE_MODE"
}

# Stage 4: Create systemd service
stage_systemd() {
    step "Этап 4/5: Настройка системного сервиса"
    
    local sudo_available=0
    if [[ $EUID -eq 0 ]]; then
        sudo_available=1
    elif command -v sudo >/dev/null 2>&1 && sudo -n -v 2>/dev/null; then
        sudo_available=1
    fi
    
    if [[ "$SERVICE_USER_MODE" == "root" && $EUID -ne 0 ]]; then
        warn "Запуск от root требует sudo"
    fi
    
    if [[ $sudo_available -eq 0 && "$SERVICE_USER_MODE" != "current" ]]; then
        echo "  sudo недоступен. Варианты:"
        echo "    1) User-level systemd сервис (без sudo, запускается при логине пользователя)"
        echo "    2) Только ручной запуск (bash start.sh)"
        echo "    3) Пропустить systemd"
        while true; do
            read -rp "Выбор [1-3]: " choice
            case "$choice" in
                1) SYSTEMD_MODE="user"; break ;;
                2) SYSTEMD_MODE="manual"; break ;;
                3) SYSTEMD_MODE="skip"; break ;;
                *) echo "Неверный выбор" ;;
            esac
        done
    else
        echo "  1) Системный systemd сервис (требует sudo)"
        echo "  2) User-level systemd сервис (без sudo)"
        echo "  3) Только ручной запуск"
        while true; do
            read -rp "Выбор [1-3]: " choice
            case "$choice" in
                1) SYSTEMD_MODE="system"; break ;;
                2) SYSTEMD_MODE="user"; break ;;
                3) SYSTEMD_MODE="manual"; break ;;
                *) echo "Неверный выбор" ;;
            esac
        done
    fi
    save_state "{\"systemd_mode\":\"$SYSTEMD_MODE\"}"
    ok "Systemd: $SYSTEMD_MODE"
}

# Stage 5: Confirmation
stage_confirm() {
    step "Этап 5/5: Подтверждение"
    echo "  Пользователь: $SERVICE_USER ($SERVICE_USER_MODE)"
    echo "  Python: $PYTHON_VER"
    echo "  Интерфейс: $INTERFACE_MODE"
    echo "  Systemd: $SYSTEMD_MODE"
    echo ""
    read -rp "Всё верно? Начать установку? [y/N]: " confirm
    [[ "${confirm,,}" == "y" || "${confirm,,}" == "yes" ]] || die "Отменено пользователем"
    save_state "{\"confirmed\":True}"
}

# Run Python installer with collected options
run_python_installer() {
    step "Запуск Python установщика..."
    
    # Get service name (generate if new, load if existing)
    local service_name
    service_name=$(get_service_name)
    info "Systemd service name: $service_name"
    
    # Bootstrap uv
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
    
    export UV_PYTHON_INSTALL_DIR="$SHIZU_ROOT/.installer/python"
    export UV_CACHE_DIR="$SHIZU_ROOT/.installer/cache"
    
    local args=()
    [[ "$PYTHON_VER" != "auto" ]] && args+=(--python "$PYTHON_VER") || args+=(--auto)
    [[ "$INTERFACE_MODE" == "terminal" ]] && args+=(--no-web)
    [[ "$SYSTEMD_MODE" == "skip" ]] && args+=(--skip-systemd)
    [[ "$SYSTEMD_MODE" == "user" ]] && args+=(--skip-systemd)  # handled separately
    
    # Pass service name
    args+=(--service-name "$service_name")
    
    # Pass service user info
    case "$SERVICE_USER_MODE" in
        root) args+=(--root) ;;
        create) args+=(--create-user "$SERVICE_USER") ;;
        current) args+=(--service-user "$SERVICE_USER") ;;
    esac
    
    exec python3 "$SHIZU_ROOT/scripts/shizu_installer.py" "${args[@]}"
}

# Handle reinstall / update / remove
handle_existing() {
    local service_name
    service_name=$(get_service_name)
    show_main_menu
    
    if [[ -n "${REINSTALL:-}" ]]; then
        step "Переустановка (сессия Telegram сохраняется)..."
        # Stop and disable the service before removal
        sudo systemctl stop "$service_name" 2>/dev/null || true
        sudo systemctl disable "$service_name" 2>/dev/null || true
        systemctl --user stop "$service_name" 2>/dev/null || true
        systemctl --user disable "$service_name" 2>/dev/null || true
        
        # Remove venv and installer, keep data
        rm -rf "$SHIZU_ROOT/.venv" "$SHIZU_ROOT/.installer" "$SHIZU_ROOT/.venv.next"
        for old in "$SHIZU_ROOT"/.venv.old.*; do
            [[ -d "$old" ]] && rm -rf "$old"
        done
        # Remove systemd unit if exists
        if [[ -f "/etc/systemd/system/$service_name" ]]; then
            sudo rm -f "/etc/systemd/system/$service_name" 2>/dev/null || rm -f "/etc/systemd/system/$service_name" 2>/dev/null
            sudo systemctl daemon-reload 2>/dev/null || systemctl daemon-reload 2>/dev/null
        fi
        # Remove user service
        rm -f "$HOME/.config/systemd/user/$service_name"
        systemctl --user daemon-reload 2>/dev/null || true
        
        # Reset state but keep telegram session info
        python3 -c "
import json, os
state_file = '$STATE_FILE'
if os.path.exists(state_file):
    with open(state_file) as f:
        data = json.load(f)
    # Keep telegram session related data
    keep = {k: data[k] for k in ('telegram_session', 'api_id', 'api_hash') if k in data}
    with open(state_file, 'w') as f:
        json.dump(keep, f, indent=2)
"
        exec bash "$SHIZU_ROOT/install.sh"  # Restart installer
        return
    fi
    
    if [[ -n "${FULL_REMOVE_KEEP_SESSION:-}" ]]; then
        step "Удаление всего (сессия Telegram сохраняется)..."
        read -rp "Точно удалить ВСЁ кроме сессии Telegram? [yes/NO]: " confirm
        [[ "$confirm" == "yes" ]] || die "Отменено"
        
        # Stop and disable the service
        sudo systemctl stop "$service_name" 2>/dev/null || true
        sudo systemctl disable "$service_name" 2>/dev/null || true
        systemctl --user stop "$service_name" 2>/dev/null || true
        systemctl --user disable "$service_name" 2>/dev/null || true
        
        rm -rf "$SHIZU_ROOT/.venv" "$SHIZU_ROOT/.installer" "$SHIZU_ROOT/.venv.next" "$SHIZU_ROOT/config.ini" "$SHIZU_ROOT/data" "$SHIZU_ROOT/sessions" "$SHIZU_ROOT/backup.key"
        for old in "$SHIZU_ROOT"/.venv.old.*; do [[ -d "$old" ]] && rm -rf "$old"; done
        sudo rm -f "/etc/systemd/system/$service_name" 2>/dev/null
        sudo systemctl daemon-reload 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/$service_name"
        systemctl --user daemon-reload 2>/dev/null || true
        rm -rf "$SHIZU_ROOT/.installer"
        ok "Всё удалено, сессия Telegram сохранена"
        exit 0
    fi
    
    if [[ -n "${FULL_REMOVE_ALL:-}" ]]; then
        step "Полное удаление (остаётся только исходный код)..."
        read -rp "Точно удалить ВСЁ кроме исходного кода? [yes/NO]: " confirm
        [[ "$confirm" == "yes" ]] || die "Отменено"
        
        # Stop and disable the service
        sudo systemctl stop "$service_name" 2>/dev/null || true
        sudo systemctl disable "$service_name" 2>/dev/null || true
        systemctl --user stop "$service_name" 2>/dev/null || true
        systemctl --user disable "$service_name" 2>/dev/null || true
        
        rm -rf "$SHIZU_ROOT/.venv" "$SHIZU_ROOT/.installer" "$SHIZU_ROOT/.venv.next" "$SHIZU_ROOT/config.ini" "$SHIZU_ROOT/data" "$SHIZU_ROOT/sessions" "$SHIZU_ROOT/backup.key" "$SHIZU_ROOT/shizu.session" "$SHIZU_ROOT/telethon_sessions.key" "$SHIZU_ROOT/telethon_sessions.sqlite3"
        for old in "$SHIZU_ROOT"/.venv.old.*; do [[ -d "$old" ]] && rm -rf "$old"; done
        sudo rm -f "/etc/systemd/system/$service_name" 2>/dev/null
        sudo systemctl daemon-reload 2>/dev/null || true
        rm -f "$HOME/.config/systemd/user/$service_name"
        systemctl --user daemon-reload 2>/dev/null || true
        rm -rf "$SHIZU_ROOT/.installer"
        ok "Всё удалено, остался только исходный код"
        exit 0
    fi
    
    if [[ -n "${SKIP_INSTALL:-}" ]]; then
        step "Запуск Shizu..."
        exec bash start.sh
    fi
    
    if [[ -n "${CHECK_UPDATE:-}" ]]; then
        step "Проверка обновлений с GitHub..."
        cd "$SHIZU_ROOT"
        local current_branch
        current_branch=$(git branch --show-current 2>/dev/null || echo "main")
        info "Текущая ветка: $current_branch"
        git fetch origin "$current_branch" 2>/dev/null || die "Не удалось получить обновления"
        local behind
        behind=$(git rev-list --count HEAD..origin/"$current_branch" 2>/dev/null || echo "0")
        if [[ "$behind" -gt 0 ]]; then
            info "Доступно обновлений: $behind коммитов"
            read -rp "Обновиться? [y/N]: " confirm
            [[ "${confirm,,}" == "y" ]] || exit 0
            git pull origin "$current_branch" || die "Ошибка обновления"
            ok "Обновлено. Перезапуск установщика..."
            exec "$0"
        else
            ok "Уже актуально"
        fi
        exit 0
    fi
}

# Main
main() {
    if check_existing; then
        handle_existing
    fi
    
    # Fresh installation
    stage_user
    stage_python
    stage_interface
    stage_systemd
    stage_confirm
    run_python_installer
}

main "$@"