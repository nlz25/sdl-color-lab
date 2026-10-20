"""Launch the packaged local UI from any working directory."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def health(url):
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=2) as response:
            result = json.load(response)
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def is_our_server(result, root=ROOT):
    return (
        result.get("app") == "color-mixing"
        and result.get("status") == "ok"
        and result.get("project_root") == str(root.resolve())
    )


def uv_command():
    binary = shutil.which("uv")
    if binary:
        return [binary]
    for candidate in (
        Path.home() / ".local/bin/uv",
        Path.home() / ".local/bin/uv.exe",
        ROOT / ".bootstrap-uv/bin/uv",
        ROOT / ".bootstrap-uv/Scripts/uv.exe",
    ):
        if candidate.is_file():
            return [str(candidate)]
    if importlib.util.find_spec("uv") is not None:
        return [sys.executable, "-m", "uv"]
    print("First launch: installing uv in an isolated environment inside this project.")
    bootstrap = ROOT / ".bootstrap-uv"
    subprocess.run([sys.executable, "-m", "venv", str(bootstrap)], check=True)
    python = bootstrap / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "uv"], check=True)
    return [str(python), "-m", "uv"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the SDL Color Lab local page")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    url = f"http://127.0.0.1:{args.port}"
    if is_our_server(health(url)):
        print(f"SDL Color Lab is already running at {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise OSError(
                f"Port {args.port} is in use by another service. Stop that service "
                "or choose another port with --port. A server from another project will not be reused."
            )
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise OSError("Frontend build not found. Run python scripts/build_frontend.py first.")
    uv = uv_command()
    backend = str(ROOT / "backend")
    env = {
        **os.environ,
        "COLOR_LAB_PROJECT_ROOT": str(ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    print("Checking locked dependencies; the first launch needs internet access to download Python and packages.")
    subprocess.run(
        [*uv, "sync", "--project", backend, "--locked", "--no-dev"],
        check=True,
        cwd=ROOT,
        env=env,
    )
    print(f"Starting SDL Color Lab at {url}", flush=True)
    process = subprocess.Popen(
        [
            *uv,
            "run",
            "--project",
            backend,
            "--locked",
            "--no-dev",
            "python",
            "-m",
            "uvicorn",
            "sdl_color_lab.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
        ],
        cwd=ROOT,
        env=env,
    )
    if not args.no_browser:

        def open_when_ready():
            for _ in range(120):
                if process.poll() is not None:
                    return
                if is_our_server(health(url)):
                    webbrowser.open(url)
                    return
                time.sleep(0.5)

        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
