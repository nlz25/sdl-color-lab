"""Build the React frontend; Node is not required for field operation."""

from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit(
            "请先安装 Node.js 22.12 或更新版本（正常使用交付包无需 Node）。"
        )
    for command in (["ci"], ["run", "build"]):
        subprocess.run([npm, *command], cwd=ROOT / "frontend", check=True)


if __name__ == "__main__":
    main()
