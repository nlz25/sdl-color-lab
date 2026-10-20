"""Build the React frontend; Node is not required for field operation."""

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit(
            "Install Node.js 22.12 or newer to build the frontend. A built copy does not need Node.js for daily operation."
        )
    for command in (["ci"], ["run", "build"]):
        subprocess.run([npm, *command], cwd=ROOT / "frontend", check=True)


if __name__ == "__main__":
    main()
