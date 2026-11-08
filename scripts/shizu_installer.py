#!/usr/bin/env python3
"""Shizu installer — stage 1: Python, venv, dependencies, systemd, then stage 2 login."""
from __future__ import annotations

import argparse
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None

ROOT = Path(__file__).resolve().parent.parent
INSTALLER_DIR = ROOT / ".installer"
PY_DIR = INSTALLER_DIR / "python"
CACHE_DIR = INSTALLER_DIR / "cache"
STATE_FILE = INSTALLER_DIR / "state.json"
CONFIG_TOML = ROOT / "shizu-installer.toml"
VENV = ROOT / ".venv"
VENV_NEXT = ROOT / ".venv.next"
START_SH = ROOT / "start.sh"
INSTALL_PY = ROOT / "scripts" / "install.py"

SUPPORTED = ("3.11", "3.12", "3.13", "3.14")
MIN_PY = "3.11"
MAX_PY = "3.14"
DEFAULT_PY = "3.11"


def log(msg: str) -> None:
    print(f"[shizu-installer] {msg}", flush=True)


def die(msg: str) -> None:
    print(f"[shizu-installer] error: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def confirm(prompt: str, yes: bool, non_interactive: bool) -> bool:
    if yes or non_interactive:
        return True
    try:
        ans = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def run(cmd: list[str], dry: bool = False, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    log("+ " + " ".join(cmd))
    if dry:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(cmd, check=check, env=env or os.environ, text=True)


def load_config() -> dict:
    if not CONFIG_TOML.exists():
        die(f"{CONFIG_TOML} not found")
    if tomllib is None:
        die("tomllib unavailable (need Python 3.11+) to read installer config")
    with CONFIG_TOML.open("rb") as f:
        data = tomllib.load(f)
    py = data.get("python", {})
    matrix = data.get("matrix", {})
    supported = tuple(matrix.get("supported", SUPPORTED))
    return {
        "min": py.get("min", MIN_PY),
        "max": py.get("max", MAX_PY),
        "default": py.get("default", DEFAULT_PY),
        "supported": supported,
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_state(state: dict, dry: bool = False) -> None:
    if dry:
        return
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def uv_bin() -> str:
    uv = os.environ.get("SHIZU_UV") or which("uv")
    if not uv:
        candidate = ROOT / ".installer" / "bin" / "uv"
        if candidate.exists():
            uv = str(candidate)
    if not uv:
        die("uv is required but not found. Run install.sh which bootstraps uv.")
    return uv


def uv_env() -> dict:
    env = dict(os.environ)
    env["UV_PYTHON_INSTALL_DIR"] = str(PY_DIR)
    env["UV_CACHE_DIR"] = str(CACHE_DIR)
    return env


def system_pythons() -> dict[str, str]:
    found: dict[str, str] = {}
    for ver in SUPPORTED:
        for cand in (f"python{ver}", f"python{ver}.0"):
            p = which(cand)
            if p:
                found[ver] = p
                break
    return found


def managed_pythons(uv: str) -> dict[str, str]:
    found: dict[str, str] = {}
    if not PY_DIR.exists():
        return found
    for ver in SUPPORTED:
        cand = PY_DIR / ver / "bin" / "python"
        if cand.exists():
            found[ver] = str(cand)
    return found


def python_version(python: str) -> str | None:
    try:
        out = subprocess.run([python, "-V"], capture_output=True, text=True, check=True).stdout.strip()
        # Python 3.11.0 -> 3.11
        parts = out.split()[1].split(".")
        return f"{parts[0]}.{parts[1]}"
    except Exception:
        return None


def discover_pythons(uv: str) -> dict[str, dict]:
    """ver -> {source, path}"""
    result: dict[str, dict] = {}
    for ver, path in system_pythons().items():
        result[ver] = {"source": "system", "path": path}
    for ver, path in managed_pythons(uv).items():
        if ver not in result:
            result[ver] = {"source": "uv-managed", "path": path}
    return result


def ensure_python(ver: str, uv: str, dry: bool) -> str:
    """Return a usable python path for ver, installing via uv if needed."""
    pythons = discover_pythons(uv)
    if ver in pythons:
        return pythons[ver]["path"]
    log(f"Python {ver} not found locally; installing via uv managed python")
    run([uv, "python", "install", ver], dry=dry, env=uv_env())
    pythons = discover_pythons(uv)
    if ver in pythons:
        return pythons[ver]["path"]
    die(f"Failed to install Python {ver}")


def choose_version(args: argparse.Namespace, cfg: dict, pythons: dict, uv: str, dry: bool) -> str:
    if args.python != "auto":
        ver = args.python
        if ver not in SUPPORTED:
            die(f"--python {ver} not supported. Supported: {', '.join(SUPPORTED)}")
        ensure_python(ver, uv, dry)
        return ver

    # --auto: лучшая доступная версия, от самой высокой к самой низкой (3.14 -> 3.11)
    for ver in reversed(cfg["supported"]):
        if ver in pythons:
            log(f"--auto: using installed Python {ver}")
            return ver
    # none installed -> install default
    default = cfg["default"] if cfg["default"] in SUPPORTED else DEFAULT_PY
    log(f"--auto: no supported Python installed; installing {default}")
    ensure_python(default, uv, dry)
    return default


def venv_python() -> str | None:
    if VENV.exists():
        cand = VENV / "bin" / "python"
        if cand.exists():
            return str(cand)
    return None


def venv_version() -> str | None:
    py = venv_python()
    if not py:
        return None
    return python_version(py)


def ensure_venv(ver: str, uv: str, rebuild: bool, dry: bool) -> str:
    python = ensure_python(ver, uv, dry)
    current = venv_version()

    if VENV.exists() and not rebuild:
        if current == ver:
            log(f"Existing .venv already on Python {ver}")
            return str(VENV / "bin" / "python")
        log(f"Existing .venv is on Python {current or '?'}; rebuilding to {ver}")
        rebuild = True

    if not VENV.exists():
        log(f"Creating .venv on Python {ver}")
        rebuild = True

    if rebuild:
        if VENV.exists():
            if not dry and VENV_NEXT.exists():
                shutil.rmtree(VENV_NEXT, ignore_errors=True)
            old = ROOT / f".venv.old.{int(time.time())}"
            if not dry:
                VENV.rename(old)
                log(f"Old venv moved to {old}")
        run([uv, "venv", "--managed-python", "--python", ver, "--seed", str(VENV_NEXT)], dry=dry, env=uv_env())
        if not dry:
            if VENV.exists():
                shutil.rmtree(VENV, ignore_errors=True)
            VENV_NEXT.rename(VENV)
            log(f"Created .venv on Python {ver}")
    return str(VENV / "bin" / "python")


def install_deps(venv_py: str, dry: bool) -> None:
    run([venv_py, "-m", "pip", "install", "--upgrade", "pip"], dry=dry)
    run([venv_py, "-m", "pip", "install", "-e", str(ROOT)], dry=dry)
    run([venv_py, "-m", "pip", "check"], dry=dry)
    log("Dependencies installed and validated")


UNIT_DESCRIPTION = "Description=Shizu Telegram userbot"


def render_unit(user: str, group: str) -> str:
    venv_py = VENV / "bin" / "python"
    readonly = " ".join(
        f'"{ROOT / relative}"' for relative in (
            "shizu", "scripts", ".venv", "pyproject.toml", "start.sh", "install.sh"
        )
    )
    return f"""[Unit]
{UNIT_DESCRIPTION}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={ROOT}
ExecStart={venv_py} -u -m shizu --no-web
Environment=PYTHONUNBUFFERED=1
Environment="PATH={venv_py.parent}:{os.defpath}"
Restart=on-failure
RestartSec=10
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=yes
CapabilityBoundingSet=
AmbientCapabilities=
PrivateTmp=yes
ProtectSystem=full
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
ReadOnlyPaths={readonly}
ReadOnlyPaths="{ROOT / '.installer'}" "{ROOT / '.git'}"
ReadWritePaths="{ROOT / 'shizu' / 'modules'}"
ReadOnlyPaths="{ROOT / 'shizu' / 'modules' / 'core'}"

[Install]
WantedBy=multi-user.target
"""


def systemd_available() -> bool:
    return shutil.which("systemctl") is not None and os.path.exists("/etc/systemd/system")


def install_systemd(user: str, group: str, dry: bool, privileged: list[str]) -> None:
    if not systemd_available():
        log("systemd not available; skipping unit install")
        return
    unit_name = "shizu.service"
    unit_path = Path("/etc/systemd/system") / unit_name
    if unit_path.exists():
        log(f"{unit_path} already exists; not overwriting")
        return
    content = render_unit(user, group)
    if dry:
        log(f"(dry-run) would write {unit_path}")
        return
    tmp = Path(tempfile.gettempdir()) / unit_name
    tmp.write_text(content)
    if os.geteuid() == 0:
        shutil.copy2(tmp, unit_path)
    elif shutil.which("sudo"):
        run(["sudo", "cp", str(tmp), str(unit_path)])
    else:
        log("sudo not available; skipping systemd unit install (run as root or with sudo)")
        return
    if shutil.which("systemctl"):
        run(["sudo", "systemctl", "daemon-reload"], check=False) if os.geteuid() != 0 else run(["systemctl", "daemon-reload"], check=False)
    log(f"systemd unit file {unit_name} written (enabled/started by stage 2 login)")


def ensure_user(name: str | None, create: str | None, yes: bool, non_interactive: bool, dry: bool, privileged: list[str]) -> tuple[str, str]:
    """Return (user, group) to run the service as."""
    if name:
        try:
            rec = pwd.getpwnam(name)
        except KeyError:
            die(f"--service-user {name} does not exist")
        return rec.pw_name, rec.pw_name or "users"
    if create:
        if not yes and not non_interactive and not confirm(f"Create system user '{create}' for the Shizu service?", yes, non_interactive):
            die(f"--create-user {create} requires confirmation")
        if dry:
            log(f"(dry-run) would create system user {create}")
            return create, create
        try:
            rec = pwd.getpwnam(create)
            log(f"System user {create} already exists")
        except KeyError:
            run([*privileged, "useradd", "--system", "--create-home", "--shell", "/usr/sbin/nologin", create], check=False)
            rec = pwd.getpwnam(create)
        return rec.pw_name, rec.pw_name
    # default: current user, but never root for the service
    me = pwd.getpwuid(os.geteuid())
    if me.pw_name == "root":
        die("Refusing to run the Shizu service as root. Use --service-user or --create-user.")
    return me.pw_name, me.pw_name


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="shizu-installer", description="Shizu stage-1 installer")
    p.add_argument("--auto", action="store_true", help="best available tested Python version")
    p.add_argument("--python", default="auto", help="3.11|3.12|3.13|3.14|auto (default: auto)")
    p.add_argument("--rebuild", action="store_true", help="safely rebuild the venv")
    p.add_argument("--no-start", action="store_true", help="stop after dependencies (skip login/start)")
    p.add_argument("--start", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--no-web", action="store_true", help="terminal setup instead of web setup")
    p.add_argument("--recreate", action="store_true", help="remove old venv/installer and install fresh")
    p.add_argument("--root", action="store_true", help="allow privileged install actions")
    p.add_argument("--service-user", help="run service as existing user")
    p.add_argument("--create-user", help="create a new system user for the service")
    p.add_argument("--yes", "-y", action="store_true", help="answer yes to all prompts")
    p.add_argument("--dry-run", action="store_true", help="print actions without executing")
    p.add_argument("--skip-systemd", action="store_true", help="do not install systemd unit")
    p.add_argument("--systemd", action="store_true", help="install systemd unit (default on Linux)")
    p.add_argument("--non-interactive", action="store_true", help="no prompts at all")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = load_config()

    if args.recreate:
        if not args.yes and not args.non_interactive and not args.dry_run:
            print("This will remove .venv, .installer, installer state and systemd unit.", flush=True)
            print("User data (config.ini, data/, sessions, backup.key) is KEPT.", flush=True)
            try:
                ans = input("Recreate installation? [y/N]: ").strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("y", "yes"):
                log("Aborted by user.")
                return 1
        if not args.dry_run:
            for p in (VENV, INSTALLER_DIR, STATE_FILE):
                if p.exists():
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
            for old in ROOT.glob(".venv.old.*"):
                shutil.rmtree(old, ignore_errors=True)
            unit_path = Path("/etc/systemd/system/shizu.service")
            if unit_path.exists():
                if os.geteuid() == 0:
                    unit_path.unlink(missing_ok=True)
                elif shutil.which("sudo"):
                    run(["sudo", "rm", "-f", str(unit_path)], check=False)
                log("Old systemd unit removed.")
            log("Old installation removed.")
        else:
            log("(dry-run) would remove .venv, .installer, state.json, systemd unit and old venvs")

    state = load_state()
    uv = uv_bin()
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    PY_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    pythons = discover_pythons(uv)
    ver = choose_version(args, cfg, pythons, uv, args.dry_run)

    venv_py = ensure_venv(ver, uv, args.rebuild, args.dry_run)
    if not args.dry_run:
        install_deps(venv_py, args.dry_run)

    state.update({"python": ver, "venv": str(VENV), "installed_at": time.time()})
    save_state(state, args.dry_run)

    privileged = [] if os.geteuid() == 0 or args.root else ["sudo"]

    do_start = not args.no_start

    if do_start:
        log("Stage 1 complete. Starting Telegram login setup (stage 2)...")
        stage2_args = [str(INSTALL_PY)]
        if args.no_web:
            stage2_args.append("--no-web")
        os.execv(venv_py, [venv_py] + stage2_args)

    log("Stage 1 complete (--no-start). Dependencies installed. Run: bash start.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
