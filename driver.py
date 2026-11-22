#!/usr/bin/env python
"""Game Theory driver - one command to run, check or benchmark the whole stack.

    python driver.py                 install if needed, start everything, open the browser
    python driver.py --check         every linter, type check and test suite
    python driver.py --bench         throughput benchmark
    python driver.py --port 8001     pin the backend port (default: first free from 8000)
    python driver.py --no-frontend   backend only
    python driver.py --no-reload     do not restart the backend on source changes
    python driver.py --install       install dependencies and exit

Stdlib only, so it runs with the system Python before anything is installed.
Ctrl+C stops both servers and their children.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import suppress
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 5173
PORT_SEARCH_RANGE = 20
IS_WINDOWS = os.name == "nt"

RESET = "\033[0m"
COLORS = {"backend": "\033[36m", "frontend": "\033[35m", "driver": "\033[32m", "warn": "\033[33m"}


def _enable_ansi() -> bool:
    """Turn on VT processing on Windows consoles; return whether colour works."""
    if not sys.stdout.isatty():
        return False
    if not IS_WINDOWS:
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
    except Exception:
        return False


def _use_utf8() -> None:
    """Make stdout able to carry whatever the child processes print.

    Vite announces itself with an arrow, and a Windows console on a non-Latin
    code page (cp1255 here) cannot encode it. That raised UnicodeEncodeError
    inside the output pump thread, which killed the thread - so the servers
    kept running but their logs went silent halfway through startup.
    Reconfiguring to UTF-8 with replacement means a character we cannot show
    costs us one "?", never a log stream.
    """
    for stream in (sys.stdout, sys.stderr):
        with suppress(AttributeError, OSError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


_use_utf8()
COLOUR = _enable_ansi()


def say(channel: str, message: str) -> None:
    """Print one prefixed, optionally coloured line.

    Never raises: a line we cannot print is not worth losing the stream over
    (see `_use_utf8`), and this runs on a daemon thread per child process.
    """
    prefix = f"{COLORS.get(channel, '')}[{channel:>8}]{RESET}" if COLOUR else f"[{channel:>8}]"
    try:
        print(f"{prefix} {message}", flush=True)
    except (UnicodeEncodeError, ValueError, OSError):
        safe = message.encode("ascii", "replace").decode("ascii")
        with suppress(Exception):
            print(f"{prefix} {safe}", flush=True)


# --------------------------------------------------------------------- tooling


def require(tool: str, install_hint: str) -> str:
    """Return the path to `tool`, or exit with an actionable message."""
    found = shutil.which(tool)
    if not found:
        say("warn", f"{tool!r} not found on PATH. {install_hint}")
        raise SystemExit(1)
    return found


def npm_command() -> str:
    """npm is a shell script on Windows, so it must be resolved explicitly."""
    return require("npm.cmd" if IS_WINDOWS else "npm", "Install Node 22 LTS: https://nodejs.org")


def port_is_free(port: int) -> bool:
    """True when nothing is listening on `port`."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def pick_port(preferred: int, *, pinned: bool) -> int:
    """Return `preferred` if free, else the next free port (unless pinned)."""
    if port_is_free(preferred):
        return preferred
    if pinned:
        say("warn", f"port {preferred} is already in use - stop that process or pick another")
        raise SystemExit(1)
    for candidate in range(preferred + 1, preferred + PORT_SEARCH_RANGE):
        if port_is_free(candidate):
            say("driver", f"port {preferred} is busy (Apache? IIS?) - using {candidate} instead")
            return candidate
    say("warn", f"no free port in {preferred}..{preferred + PORT_SEARCH_RANGE}")
    raise SystemExit(1)


# ------------------------------------------------------------------- processes


class Managed:
    """A child process whose output is streamed with a prefix."""

    def __init__(self, name: str, command: list[str], cwd: Path, env: dict[str, str]) -> None:
        self.name = name
        self.command = command
        creation = subprocess.CREATE_NEW_PROCESS_GROUP if IS_WINDOWS else 0
        self.process = subprocess.Popen(  # noqa: S603 - fixed commands, no user input
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
        )
        self.pump = threading.Thread(target=self._pump, name=f"{name}-output", daemon=True)
        self.pump.start()

    def _pump(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        for line in stream:
            line = line.rstrip()
            if line:
                say(self.name, line)

    @property
    def alive(self) -> bool:
        """Whether the process is still running."""
        return self.process.poll() is None

    def stop(self) -> None:
        """Terminate the process and everything it spawned."""
        if not self.alive:
            return
        if IS_WINDOWS:
            # uvicorn --reload and vite both spawn children; kill the tree.
            subprocess.run(  # noqa: S603 - fixed command
                ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                capture_output=True,
                check=False,
            )
        else:
            self.process.terminate()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()


def run_step(label: str, command: list[str], cwd: Path) -> bool:
    """Run a command to completion, streaming output. Return True on success."""
    say("driver", f"{label}: {' '.join(command)}")
    result = subprocess.run(command, cwd=cwd, check=False)  # noqa: S603 - fixed commands
    if result.returncode != 0:
        say("warn", f"{label} FAILED (exit {result.returncode})")
        return False
    return True


# -------------------------------------------------------------------- installs


def install_backend(uv: str) -> None:
    """Sync backend dependencies if the virtualenv is missing."""
    if (BACKEND / ".venv").exists():
        return
    say("driver", "installing backend dependencies (first run)")
    if not run_step("uv sync", [uv, "sync"], BACKEND):
        raise SystemExit(1)


def install_frontend(npm: str) -> None:
    """Install frontend dependencies if node_modules is missing."""
    if (FRONTEND / "node_modules").exists():
        return
    say("driver", "installing frontend dependencies (first run, ~1 minute)")
    if not run_step("npm install", [npm, "install"], FRONTEND):
        raise SystemExit(1)


# ----------------------------------------------------------------- entrypoints


def wait_for_url(url: str, timeout: float, child: Managed | None = None) -> bool:
    """Poll `url` until it answers, `timeout` elapses, or `child` dies."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child is not None and not child.alive:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310 - localhost
                if response.status == 200:
                    return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.4)
    return False


WATCH_SUFFIXES = (".py", ".yaml", ".yml")
WATCH_DEBOUNCE_S = 0.6


def source_stamp(roots: tuple[Path, ...]) -> dict[str, float]:
    """Modification times of every watched source file under `roots`."""
    stamp: dict[str, float] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in WATCH_SUFFIXES or "__pycache__" in path.parts:
                continue
            try:
                stamp[str(path)] = path.stat().st_mtime
            except OSError:
                continue
    return stamp


def start_backend(uv: str, port: int, env: dict[str, str]) -> Managed:
    """Launch the backend without uvicorn's own reloader.

    `uvicorn --reload` does not work for this app on Windows: the reloader
    announces "Reloading..." and then never finishes, because the worker
    process never exits. The old worker keeps serving, so an edit silently
    has no effect - which is worse than a crash, since the server looks
    healthy while running code you have already changed. The driver watches
    the files and restarts the whole process instead; a tree kill is a thing
    we already do reliably (see `Managed.stop`).
    """
    return Managed(
        "backend",
        [uv, "run", "uvicorn", "app.main:app", "--port", str(port)],
        BACKEND,
        env,
    )


def serve(
    backend_port: int,
    frontend_port: int,
    *,
    frontend: bool,
    browser: bool,
    reload: bool = True,
) -> int:
    """Start the servers and block until they exit or Ctrl+C."""
    uv = require("uv", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    install_backend(uv)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    children: list[Managed] = []
    try:
        backend_process = start_backend(uv, backend_port, env)
        children.append(backend_process)

        if not wait_for_url(
            f"http://127.0.0.1:{backend_port}/api/health", timeout=60.0, child=backend_process
        ):
            say("warn", "backend did not answer /api/health - see the log above")
            return 1
        say("driver", f"backend ready  -> http://localhost:{backend_port}/docs")

        if frontend:
            npm = npm_command()
            install_frontend(npm)
            frontend_env = env.copy()
            # Point Vite's proxy at whichever port the backend actually got.
            frontend_env["VITE_BACKEND_URL"] = f"http://localhost:{backend_port}"
            frontend_process = Managed(
                "frontend",
                [npm, "run", "dev", "--", "--port", str(frontend_port), "--strictPort"],
                FRONTEND,
                frontend_env,
            )
            children.append(frontend_process)

            # Verify, never assume: Vite can fail on a busy port seconds after
            # starting, and announcing a URL that 404s is worse than waiting.
            url = f"http://localhost:{frontend_port}"
            if not wait_for_url(url, timeout=90.0, child=frontend_process):
                say("warn", f"frontend did not come up on {url} - see the log above")
                return 1
            say("driver", f"frontend ready -> {url}")
            if browser:
                webbrowser.open(url)

        watched = (BACKEND / "app", BACKEND / "config")
        stamp = source_stamp(watched) if reload else {}
        say("driver", "Ctrl+C to stop" + ("  (watching backend sources)" if reload else ""))

        while all(child.alive for child in children):
            time.sleep(0.4)
            if not reload:
                continue
            current = source_stamp(watched)
            if current == stamp:
                continue
            # Let a burst of saves settle before paying for a restart.
            time.sleep(WATCH_DEBOUNCE_S)
            current = source_stamp(watched)
            changed = sorted(
                name
                for name in set(current) | set(stamp)
                if current.get(name) != stamp.get(name)
            )
            stamp = current
            say("driver", f"reloading backend ({len(changed)} file(s) changed)")
            for name in changed[:3]:
                say("driver", f"  {Path(name).relative_to(ROOT)}")

            backend_process.stop()
            children.remove(backend_process)
            backend_process = start_backend(uv, backend_port, env)
            children.insert(0, backend_process)
            if wait_for_url(
                f"http://127.0.0.1:{backend_port}/api/health",
                timeout=60.0,
                child=backend_process,
            ):
                say("driver", "backend reloaded")
            else:
                say("warn", "backend did not come back after the reload - see the log above")
                return 1

        for child in children:
            if not child.alive:
                say("warn", f"{child.name} exited with code {child.process.returncode}")
        return 1
    except KeyboardInterrupt:
        say("driver", "stopping...")
        return 0
    finally:
        for child in reversed(children):
            child.stop()
        say("driver", "stopped")


def check() -> int:
    """Run every linter, type check and test suite. Returns a process exit code."""
    uv = require("uv", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    npm = npm_command()
    install_backend(uv)
    install_frontend(npm)

    steps: list[tuple[str, list[str], Path]] = [
        ("ruff format", [uv, "run", "ruff", "format", "--check", "."], BACKEND),
        ("ruff check", [uv, "run", "ruff", "check", "."], BACKEND),
        # Tests are type-checked too, under the same strict settings: a
        # mistyped test is a test that passes for the wrong reason.
        ("mypy", [uv, "run", "mypy", "app", "tests"], BACKEND),
        ("import-linter", [uv, "run", "lint-imports"], BACKEND),
        ("pytest", [uv, "run", "pytest"], BACKEND),
        ("tsc", [npm, "run", "typecheck"], FRONTEND),
        ("eslint", [npm, "run", "lint"], FRONTEND),
        ("vitest", [npm, "run", "test"], FRONTEND),
        ("vite build", [npm, "run", "build"], FRONTEND),
    ]

    failed = [label for label, command, cwd in steps if not run_step(label, command, cwd)]
    print()
    if failed:
        say("warn", f"{len(failed)} of {len(steps)} checks failed: {', '.join(failed)}")
        return 1
    say("driver", f"all {len(steps)} checks passed")
    return 0


def bench(agents: list[int], ticks: int) -> int:
    """Run the headless throughput benchmark."""
    uv = require("uv", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    install_backend(uv)
    command = [uv, "run", "python", "-m", "app.tools.bench", "--ticks", str(ticks), "--agents"]
    command += [str(count) for count in agents]
    return 0 if run_step("bench", command, BACKEND) else 1


def main() -> int:
    """Parse arguments and dispatch."""
    parser = argparse.ArgumentParser(
        description="Run, check or benchmark Game Theory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--port", type=int, default=None, help="Backend port (default: 8000).")
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--no-frontend", action="store_true", help="Run the backend only.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser.")
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Do not restart the backend when its sources change.",
    )
    parser.add_argument("--install", action="store_true", help="Install dependencies and exit.")
    parser.add_argument("--check", action="store_true", help="Run all linters, types and tests.")
    parser.add_argument("--bench", action="store_true", help="Run the throughput benchmark.")
    parser.add_argument("--agents", type=int, nargs="+", default=[100, 500, 1000])
    parser.add_argument("--ticks", type=int, default=1000)
    args = parser.parse_args()

    if not BACKEND.is_dir() or not FRONTEND.is_dir():
        say("warn", f"run this from the repo root (expected {BACKEND} and {FRONTEND})")
        return 1

    if args.install:
        uv = require("uv", "Install uv: https://docs.astral.sh/uv/")
        install_backend(uv)
        install_frontend(npm_command())
        say("driver", "dependencies installed")
        return 0

    if args.check:
        return check()

    if args.bench:
        return bench(args.agents, args.ticks)

    backend_port = pick_port(args.port or DEFAULT_BACKEND_PORT, pinned=args.port is not None)
    # Vite is pinned with --strictPort, so a stale dev server has to be dealt
    # with rather than silently worked around on another port.
    if not port_is_free(args.frontend_port):
        say("warn", f"port {args.frontend_port} is in use - a dev server is probably still running")
        say("warn", "stop it, or pass --frontend-port <other>")
        return 1
    frontend_port = args.frontend_port
    return serve(
        backend_port,
        frontend_port,
        frontend=not args.no_frontend,
        browser=not args.no_browser,
        reload=not args.no_reload,
    )


if __name__ == "__main__":
    raise SystemExit(main())
