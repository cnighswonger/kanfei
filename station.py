#!/usr/bin/env python3
"""Cross-platform setup and run script for Davis Weather Station.

Works on Windows 10+, macOS, and Linux without make, bash, or
any platform-specific tooling beyond Python 3.10+ and Node.js.

Usage:
    python station.py setup       Install all dependencies and build frontend
    python station.py run         Start the production server
    python station.py dev         Start backend + frontend dev servers
    python station.py test        Run backend tests
    python station.py clean       Remove build artifacts and caches
    python station.py status      Check installation state
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform detection and paths
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"
ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = BACKEND_DIR / ".venv"

if IS_WINDOWS:
    VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
    VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"
    VENV_UVICORN = VENV_DIR / "Scripts" / "uvicorn.exe"
else:
    VENV_PYTHON = VENV_DIR / "bin" / "python"
    VENV_PIP = VENV_DIR / "bin" / "pip"
    VENV_UVICORN = VENV_DIR / "bin" / "uvicorn"

MIN_PYTHON = (3, 10)
MIN_NODE = 18

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def heading(msg: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {msg}")
    print(f"{'=' * 60}\n")


def step(msg: str) -> None:
    print(f"  -> {msg}")


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [!!] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}", file=sys.stderr)


def run_cmd(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    check: bool = True,
    quiet: bool = False,
) -> subprocess.CompletedProcess:
    """Run a subprocess, using shell=True on Windows for .cmd/.bat scripts."""
    # On Windows, npm/npx are .cmd files and need shell=True
    needs_shell = IS_WINDOWS and any(
        c.endswith((".cmd", ".bat")) or c in ("npm", "npx", "node")
        for c in cmd[:1]
    )
    kwargs: dict = {
        "cwd": str(cwd) if cwd else None,
        "check": check,
        "shell": needs_shell,
    }
    if env:
        merged = {**os.environ, **env}
        kwargs["env"] = merged
    if quiet:
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    return subprocess.run(cmd, **kwargs)


def find_npm() -> str | None:
    """Locate npm executable."""
    return shutil.which("npm")


def get_node_version() -> int | None:
    """Return the major Node.js version, or None if not installed."""
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.check_output([node, "--version"], text=True).strip()
        # e.g. "v20.11.0"
        return int(out.lstrip("v").split(".")[0])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Prerequisites check
# ---------------------------------------------------------------------------


def check_prerequisites() -> bool:
    """Verify Python and Node.js are available and meet minimum versions."""
    heading("Checking prerequisites")
    all_ok = True

    # Python
    v = sys.version_info
    if v >= MIN_PYTHON:
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor} found — need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+")
        all_ok = False

    # Node.js
    node_ver = get_node_version()
    if node_ver is None:
        fail("Node.js not found — install from https://nodejs.org")
        all_ok = False
    elif node_ver < MIN_NODE:
        fail(f"Node.js v{node_ver} found — need v{MIN_NODE}+")
        all_ok = False
    else:
        ok(f"Node.js v{node_ver}")

    # npm
    npm = find_npm()
    if npm:
        ok(f"npm found at {npm}")
    else:
        fail("npm not found")
        all_ok = False

    return all_ok


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_setup(_args: argparse.Namespace) -> int:
    """Install everything: venv, Python deps, Node deps, build frontend."""
    if not check_prerequisites():
        return 1

    # 1. Python virtual environment
    heading("Creating Python virtual environment")
    if VENV_PYTHON.exists():
        ok(f"venv already exists at {VENV_DIR}")
    else:
        step(f"Creating venv in {VENV_DIR}")
        venv.create(str(VENV_DIR), with_pip=True)
        ok("venv created")

    # 2. Python dependencies
    heading("Installing Python dependencies")
    step("Upgrading pip")
    run_cmd([str(VENV_PIP), "install", "--upgrade", "pip"])
    step("Installing backend package with dev extras")
    run_cmd([str(VENV_PIP), "install", "-e", f"{BACKEND_DIR}[dev]"])
    ok("Python dependencies installed")

    # 3. Node dependencies
    heading("Installing Node dependencies")
    run_cmd(["npm", "install"], cwd=FRONTEND_DIR)
    ok("Node dependencies installed")

    # 4. Build frontend
    heading("Building frontend for production")
    run_cmd(["npm", "run", "build"], cwd=FRONTEND_DIR)
    ok("Frontend built")

    # 5. Create .env if missing
    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        heading("Creating default .env file")
        shutil.copy2(env_example, env_file)
        if IS_WINDOWS:
            # Patch the default serial port for Windows
            text = env_file.read_text()
            text = text.replace(
                "KANFEI_SERIAL_PORT=/dev/ttyUSB0",
                "KANFEI_SERIAL_PORT=COM3",
            )
            env_file.write_text(text)
            step("Set default serial port to COM3 (edit .env to match your port)")
        ok(f"Created {env_file}")
        step("Edit .env to configure your serial port, location, etc.")

    heading("Setup complete")
    print(textwrap.dedent("""\
        Next steps:
          1. Edit .env with your serial port and location
          2. Run the server:  python station.py run
          3. Open http://localhost:8000 in your browser
    """))
    return 0


def cmd_run(_args: argparse.Namespace) -> int:
    """Start the production server (frontend served as static files)."""
    if not VENV_PYTHON.exists():
        fail("Virtual environment not found. Run:  python station.py setup")
        return 1

    frontend_dist = FRONTEND_DIR / "dist"
    if not frontend_dist.exists():
        warn("Frontend not built — building now...")
        run_cmd(["npm", "run", "build"], cwd=FRONTEND_DIR)

    heading("Starting Davis Weather Station")
    step("Server at http://localhost:8000")
    step("Press Ctrl+C to stop\n")

    # Use Popen so we can explicitly terminate the child on Ctrl+C.
    # subprocess.run() on Windows doesn't reliably forward the interrupt.
    proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"],
        cwd=str(BACKEND_DIR),
    )

    def _shutdown(signum=None, frame=None):
        proc.terminate()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    if IS_WINDOWS:
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        rc = proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
    return rc


def cmd_dev(_args: argparse.Namespace) -> int:
    """Start backend (port 8000) and frontend dev server (port 3000) together."""
    if not VENV_PYTHON.exists():
        fail("Virtual environment not found. Run:  python station.py setup")
        return 1

    heading("Starting development servers")
    step("Backend  -> http://localhost:8000")
    step("Frontend -> http://localhost:3000  (proxies API to backend)")
    step("Press Ctrl+C to stop both\n")

    # Start backend
    backend_proc = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--reload", "--log-level", "info"],
        cwd=str(BACKEND_DIR),
    )

    # Start frontend dev server
    frontend_cmd = ["npm", "run", "dev"]
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=str(FRONTEND_DIR),
        shell=IS_WINDOWS,
    )

    def cleanup(signum=None, frame=None):
        backend_proc.terminate()
        frontend_proc.terminate()

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    if IS_WINDOWS:
        signal.signal(signal.SIGBREAK, cleanup)

    # Wait for either to exit
    try:
        while True:
            be = backend_proc.poll()
            fe = frontend_proc.poll()
            if be is not None or fe is not None:
                cleanup()
                break
            backend_proc.wait(timeout=1)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        cleanup()

    backend_proc.wait()
    frontend_proc.wait()
    return 0


def cmd_test(_args: argparse.Namespace) -> int:
    """Run backend tests."""
    if not VENV_PYTHON.exists():
        fail("Virtual environment not found. Run:  python station.py setup")
        return 1

    heading("Running backend tests")
    result = run_cmd(
        [str(VENV_PYTHON), "-m", "pytest", str(ROOT / "tests" / "backend"), "-v"],
        cwd=BACKEND_DIR,
        check=False,
    )
    return result.returncode


def cmd_clean(_args: argparse.Namespace) -> int:
    """Remove build artifacts and caches."""
    heading("Cleaning build artifacts")
    targets = [
        FRONTEND_DIR / "dist",
        FRONTEND_DIR / "node_modules",
        VENV_DIR,
    ]
    for target in targets:
        if target.exists():
            step(f"Removing {target.relative_to(ROOT)}")
            shutil.rmtree(target)

    # Python caches
    for pattern in ("__pycache__", ".pytest_cache"):
        for d in ROOT.rglob(pattern):
            if d.is_dir():
                step(f"Removing {d.relative_to(ROOT)}")
                shutil.rmtree(d)

    ok("Clean complete")
    return 0


def _resolve_db_path() -> str | None:
    """Resolve the database path using the same config logic as the app."""
    sys.path.insert(0, str(BACKEND_DIR))
    try:
        from app.config import settings
        if Path(settings.db_path).exists():
            return settings.db_path
    except Exception:
        pass
    # Fallback: check common names in project root
    for name in ("kanfei.db", "weather.db"):
        candidate = ROOT / name
        if candidate.exists():
            return str(candidate)
    return None


def cmd_backup(args: argparse.Namespace) -> int:
    """Create a backup of the database and backgrounds."""
    heading("Creating backup")

    sys.path.insert(0, str(BACKEND_DIR))
    from app.services.backup import create_backup, get_backup_dir, generate_backup_filename

    db_path = _resolve_db_path()
    if db_path is None:
        fail("No database found. Is the station set up?")
        return 1

    if args.output:
        output = args.output
    else:
        backup_dir = get_backup_dir(db_path)
        output = str(Path(backup_dir) / generate_backup_filename())

    step(f"Database: {db_path}")
    step(f"Output:   {output}")

    try:
        manifest = create_backup(db_path, output)
        ok(f"Backup created: {output}")
        ok(f"  Size: {manifest['archive_size_bytes']:,} bytes")
        ok(f"  Rows: {manifest['row_counts']}")
        if manifest.get("backgrounds_count", 0) > 0:
            ok(f"  Backgrounds: {manifest['backgrounds_count']} files")
    except Exception as exc:
        fail(f"Backup failed: {exc}")
        return 1

    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore from a backup archive."""
    heading("Restoring from backup")

    if not args.input:
        fail("--input is required: path to .tar.gz backup archive")
        return 1

    archive = Path(args.input)
    if not archive.exists():
        fail(f"Archive not found: {archive}")
        return 1

    sys.path.insert(0, str(BACKEND_DIR))
    from app.services.backup import restore_backup

    # Determine target directory (where the DB lives)
    db_path = _resolve_db_path()
    target_dir = str(Path(db_path).parent) if db_path else str(ROOT)

    step(f"Archive:    {archive}")
    step(f"Target dir: {target_dir}")
    warn("This will overwrite the current database!")
    warn("A .pre-restore copy will be created as a safety net.")

    try:
        response = input("  Type RESTORE to confirm: ")
    except (EOFError, KeyboardInterrupt):
        print()
        step("Cancelled.")
        return 1

    if response.strip() != "RESTORE":
        step("Cancelled — confirmation not matched.")
        return 1

    try:
        manifest = restore_backup(str(archive), target_dir)
        ok("Restore complete!")
        ok(f"  Database: {manifest['db_file']}")
        ok(f"  From: {manifest['timestamp']}")
        step("Restart the server to use the restored data.")
    except Exception as exc:
        fail(f"Restore failed: {exc}")
        return 1

    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    """Check installation state."""
    heading("Installation status")

    # Python
    v = sys.version_info
    ok(f"Python {v.major}.{v.minor}.{v.micro}")

    # Node
    node_ver = get_node_version()
    if node_ver:
        ok(f"Node.js v{node_ver}")
    else:
        warn("Node.js not found")

    # venv
    if VENV_PYTHON.exists():
        ok(f"Python venv: {VENV_DIR}")
    else:
        warn("Python venv: not created")

    # Node modules
    nm = FRONTEND_DIR / "node_modules"
    if nm.exists():
        ok("Node modules: installed")
    else:
        warn("Node modules: not installed")

    # Frontend build
    dist = FRONTEND_DIR / "dist"
    if dist.exists():
        ok("Frontend build: ready")
    else:
        warn("Frontend build: not built")

    # .env
    env_file = ROOT / ".env"
    if env_file.exists():
        ok(f".env file: {env_file}")
    else:
        warn(".env file: not created (will use defaults)")

    # Database
    db_files = list(BACKEND_DIR.glob("*.db")) + list(ROOT.glob("*.db"))
    if db_files:
        for db in db_files:
            ok(f"Database: {db}")
    else:
        step("Database: will be created on first run")

    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="station.py",
        description="Davis Weather Station — cross-platform setup and launcher",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="Install all dependencies and build frontend")
    sub.add_parser("run", help="Start the production server")
    sub.add_parser("dev", help="Start backend + frontend dev servers")
    sub.add_parser("test", help="Run backend tests")
    sub.add_parser("clean", help="Remove build artifacts and caches")
    sub.add_parser("status", help="Check installation state")

    backup_parser = sub.add_parser("backup", help="Create a backup of DB and backgrounds")
    backup_parser.add_argument("--output", "-o", help="Output path for .tar.gz archive")

    restore_parser = sub.add_parser(
        "restore",
        help="Restore from a backup archive",
        epilog='Windows note: use forward slashes or quote paths in Git Bash, '
               'e.g. --input "C:/Users/you/backups/kanfei-backup.tar.gz"',
    )
    restore_parser.add_argument("--input", "-i", help="Path to .tar.gz backup archive")

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "run": cmd_run,
        "dev": cmd_dev,
        "test": cmd_test,
        "clean": cmd_clean,
        "status": cmd_status,
        "backup": cmd_backup,
        "restore": cmd_restore,
    }

    if args.command is None:
        parser.print_help()
        return 0

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
