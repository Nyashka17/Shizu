"""Interactive account setup and optional Linux systemd installation."""

import argparse
import configparser
import getpass
import os
import pwd
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv/bin/python"
DEFAULT_SERVICE = "shizu.service"
UNIT_DIR = Path("/etc/systemd/system")
DESCRIPTION = "Description=Shizu Telegram userbot"


def generate_service_suffix() -> str:
    """Generate a 5-character random suffix for service name."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=5))


def ask(question):
    while True:
        answer = input(question + " [y/N]: ").strip().lower()
        if answer in ("", "n", "no"):
            return False
        if answer in ("y", "yes"):
            return True


def run(*command, env=None):
    subprocess.run(command, cwd=ROOT, check=True, env=env or os.environ)


def unit_quote(value):
    # systemd specifiers are expanded even inside quotes.
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("The path contains control characters")
    return (
        '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    )


def unit_value(value):
    # User= and WorkingDirectory= take the raw value: quotes would become part of it.
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("The path contains control characters")
    return value.replace("%", "%%")


def own_unit(service_name: str):
    unit_path = UNIT_DIR / service_name
    try:
        text = unit_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return DESCRIPTION in text and str(ROOT) in text


def service_text(username):
    if username == "root":
        raise ValueError("The hardened userbot service must run as an ordinary user. Use --root to override.")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\$?", username):
        raise ValueError(f"Unsupported user name for systemd: {username!r}")
    readonly = " ".join(
        unit_quote(ROOT / relative)
        for relative in (
            "shizu", "scripts", ".venv", "pyproject.toml", "start.sh", "install.sh"
        )
    )
    return f"""[Unit]
{DESCRIPTION}
Wants=network-online.target
After=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User={username}
WorkingDirectory={unit_value(ROOT)}
ExecStart={unit_quote(PYTHON)} -u -m shizu --no-web
Environment=PYTHONUNBUFFERED=1
Environment={unit_quote("PATH=" + str(PYTHON.parent) + ":" + os.defpath)}
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
ReadOnlyPaths={unit_quote("-" + str(ROOT / ".installer"))}
ReadWritePaths={unit_quote(ROOT / ".git")} {unit_quote(ROOT / "shizu/modules")}
ReadOnlyPaths={unit_quote(ROOT / "shizu/modules/core")}

[Install]
WantedBy=multi-user.target
"""


def account_config():
    cfg = configparser.ConfigParser()
    path = ROOT / "config.ini"
    cfg.read(path)
    api_id = cfg.get("pyrogram", "api_id", fallback="")
    api_hash = cfg.get("pyrogram", "api_hash", fallback="")
    if (
        api_id.isdigit()
        and int(api_id) > 0
        and len(api_hash) == 32
        and all(c in "0123456789abcdefABCDEF" for c in api_hash)
    ):
        return
    print("\nEnter the API ID and API Hash from https://my.telegram.org/apps")
    while True:
        api_id = input("API ID: ").strip()
        if api_id.isdigit() and int(api_id) > 0:
            break
        print("API ID must be a positive number.")
    while True:
        api_hash = getpass.getpass("API Hash (hidden): ").strip()
        if len(api_hash) == 32 and all(c in "0123456789abcdefABCDEF" for c in api_hash):
            break
        print("API Hash must be 32 hexadecimal characters.")
    if not cfg.has_section("pyrogram"):
        cfg.add_section("pyrogram")
    cfg.set("pyrogram", "api_id", api_id)
    cfg.set("pyrogram", "api_hash", api_hash)
    with path.open("w", encoding="utf-8") as stream:
        cfg.write(stream)
    path.chmod(0o600)


def has_sudo() -> bool:
    """Check if sudo is available and user has passwordless sudo or can enter password."""
    if os.geteuid() == 0:
        return True
    if not shutil.which("sudo"):
        return False
    try:
        # -n = non-interactive, -v = validate
        return subprocess.run(["sudo", "-n", "-v"], capture_output=True).returncode == 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-start", action="store_true", help="Only install dependencies"
    )
    parser.add_argument(
        "--no-web", action="store_true", help="Terminal setup instead of web setup"
    )
    parser.add_argument(
        "--root", action="store_true", help="allow running Shizu service as root (not recommended)"
    )
    parser.add_argument(
        "--service-user", help="run service as existing system user"
    )
    parser.add_argument(
        "--create-user", help="create a new system user for the service"
    )
    parser.add_argument(
        "--skip-systemd", action="store_true", help="skip systemd service installation"
    )
    parser.add_argument(
        "--systemd-mode", choices=["system", "user", "manual", "skip"], help="systemd mode"
    )
    parser.add_argument(
        "--service-name", help="Custom systemd service name (default: shizu_<5random>.service)"
    )
    args = parser.parse_args()
    os.chdir(ROOT)
    os.umask(0o077)
    
    # Determine service name
    if args.service_name:
        service_name = args.service_name
        if not service_name.endswith(".service"):
            service_name += ".service"
    else:
        # Generate random suffix for new installations
        service_name = f"shizu_{generate_service_suffix()}.service"
    
    UNIT_PATH = UNIT_DIR / service_name
    print(f"\nShizu is installed. Service: {service_name}", flush=True)
    print("Start it manually with: bash start.sh", flush=True)
    if args.no_start:
        return
    if not sys.stdin.isatty():
        raise RuntimeError(
            "An interactive terminal is required. Use --no-start to install without logging in"
        )
    systemd = (
        sys.platform.startswith("linux")
        and Path("/run/systemd/system").is_dir()
        and shutil.which("systemctl")
        and not args.skip_systemd
        and args.systemd_mode != "skip"
        and args.systemd_mode != "manual"
    )
    if (
        systemd
        and subprocess.run(["systemctl", "is-active", "--quiet", service_name]).returncode
        == 0
    ):
        raise RuntimeError(
            f"The Shizu service ({service_name}) is already running. Stop it first: sudo systemctl stop {service_name}"
        )
    
    # Check sudo availability
    sudo_available = has_sudo()
    
    # Determine systemd mode from args or interactive
    if args.systemd_mode == "system":
        use_service = True
        use_user_service = False
    elif args.systemd_mode == "user":
        use_service = True
        use_user_service = True
    elif args.systemd_mode in ("manual", "skip"):
        use_service = False
        use_user_service = False
        systemd = False
    else:
        # Interactive mode
        if systemd and not sudo_available:
            print("⚠ systemd found but sudo not available. Options:")
            print("  1) Install user-level systemd service (no sudo needed)")
            print("  2) Run manually with 'bash start.sh'")
            print("  3) Skip systemd")
            choice = input("Choose [1/2/3]: ").strip()
            if choice == "1":
                use_user_service = True
                use_service = True
            elif choice == "3":
                use_service = False
                systemd = False
            else:
                use_service = False
                systemd = False
        else:
            use_service = bool(systemd) and ask(
                "Run Shizu as a systemd service that starts on boot? Requires sudo"
            )
            use_user_service = False
    
    privileged = [] if os.geteuid() == 0 else (["sudo"] if sudo_available else [])
    if use_service:
        # Determine service username
        if args.service_user:
            username = args.service_user
            try:
                pwd.getpwnam(username)
            except KeyError:
                raise RuntimeError(f"--service-user {username} does not exist")
        elif args.create_user:
            username = args.create_user
            if privileged:
                run(*privileged, "useradd", "--system", "--create-home", "--shell", "/usr/sbin/nologin", username)
        elif args.root:
            username = "root"
        else:
            username = pwd.getpwuid(os.getuid()).pw_name
            if username == "root":
                raise RuntimeError("Install Shizu as an ordinary user; a root service is refused. Use --root, --service-user, or --create-user.")
        if privileged:
            run(*privileged, "sudo", "-v")
    elif sys.platform.startswith("linux") and not systemd:
        print("systemd was not found. Start Shizu manually with bash start.sh.")
    
    # Create systemd service BEFORE Telegram login so it's ready even if login is interrupted
    if use_service:
        if use_user_service:
            # User-level systemd service (no sudo needed)
            user_unit_dir = Path.home() / ".config" / "systemd" / "user"
            user_unit_dir.mkdir(parents=True, exist_ok=True)
            user_unit_path = user_unit_dir / service_name
            unit_content = service_text(username)
            # For user service, we need to adjust paths
            unit_content = unit_content.replace("WantedBy=multi-user.target", "WantedBy=default.target")
            user_unit_path.write_text(unit_content, encoding="utf-8")
            run("systemctl", "--user", "daemon-reload")
            run("systemctl", "--user", "enable", "--now", service_name)
            print(
                f"\nShizu systemd user service created and enabled: {service_name}\n  Logs:    journalctl --user -u {service_name} -f\n  Restart: systemctl --user restart {service_name}\n  Stop:    systemctl --user stop {service_name}\n  Enable linger: loginctl enable-linger $USER",
                flush=True,
            )
        else:
            # System-level service (requires sudo)
            with tempfile.TemporaryDirectory(prefix="shizu-service-") as folder:
                unit = Path(folder) / service_name
                unit.write_text(service_text(username), encoding="utf-8")
                run(*privileged, "install", "-m", "644", str(unit), str(UNIT_PATH))
            run(*privileged, "systemctl", "daemon-reload")
            run(*privileged, "systemctl", "enable", "--now", service_name)
            print(
                f"\nShizu systemd service created and enabled: {service_name}\n  Logs:    journalctl -u {service_name} -f\n  Restart: sudo systemctl restart {service_name}\n  Stop:    sudo systemctl stop {service_name}",
                flush=True,
            )
    
    if args.no_web:
        account_config()
    print(
        "\nTelegram login: log in with a QR code or your phone number, code and 2FA password.",
        flush=True,
    )
    setup_cmd = [str(PYTHON), "-u", "-m", "shizu", "--setup-only"]
    if args.no_web:
        setup_cmd.insert(3, "--no-web")
    # Allow root if requested
    env = os.environ.copy()
    if args.root or (args.service_user and args.service_user == "root"):
        env["SHIZU_ALLOW_ROOT"] = "1"
    run(*setup_cmd, env=env)
    
    # Verify service is running after login
    if use_service:
        if use_user_service:
            if (
                subprocess.run(["systemctl", "--user", "is-active", "--quiet", service_name]).returncode
                != 0
            ):
                subprocess.run(["systemctl", "--user", "--no-pager", "status", service_name])
                raise RuntimeError(
                    f"The Shizu user service did not start. See the log: journalctl --user -u {service_name} -e"
                )
            print(
                f"\nShizu runs as a user service and starts on login.\nOpen your bot and send /panel to control Shizu from Telegram.\n",
                flush=True,
            )
        else:
            if (
                subprocess.run(["systemctl", "is-active", "--quiet", service_name]).returncode
                != 0
            ):
                subprocess.run(["systemctl", "--no-pager", "status", service_name])
                raise RuntimeError(
                    f"The Shizu service did not start. See the log: journalctl -u {service_name} -e"
                )
            print(
                f"\nShizu runs as a service and starts on boot.\nOpen your bot and send /panel to control Shizu from Telegram.\n",
                flush=True,
            )
    else:
        print(
            "\nStarting Shizu. Press Ctrl+C to stop. Next time start it with: bash start.sh",
            flush=True,
        )
        start_cmd = [str(PYTHON), "-u", "-m", "shizu"]
        if args.no_web:
            start_cmd.append("--no-web")
        os.execv(str(PYTHON), start_cmd)


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print(
            "\nInstallation stopped. Run it again with: bash install.sh",
            file=sys.stderr,
        )
        sys.exit(130)
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"\nError: {error}", file=sys.stderr)
        sys.exit(1)
