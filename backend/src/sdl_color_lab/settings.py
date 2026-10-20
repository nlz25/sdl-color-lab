"""Central paths: packaged read-only fixtures and explicitly located user data."""

from __future__ import annotations

from importlib.resources import files
import os
from pathlib import Path


def project_root() -> Path:
    configured = os.getenv("COLOR_LAB_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    # Editable install: <project>/backend/src/sdl_color_lab/settings.py.
    candidate = Path(__file__).resolve().parents[3]
    if (candidate / "backend" / "pyproject.toml").is_file():
        return candidate
    raise ValueError(
        "无法定位项目目录；独立安装后请设置 COLOR_LAB_PROJECT_ROOT 为项目根目录"
    )


def environment_file() -> Path:
    return project_root() / ".env"


def load_environment() -> None:
    """Load the one project config file without replacing explicit environment."""
    from dotenv import load_dotenv

    load_dotenv(environment_file(), override=False)


def session_directory() -> Path:
    # Preserve the old variable's meaning: it points to sessions, not runtime.
    load_environment()
    configured = os.getenv("COLOR_MIXING_DATA_DIR")
    if configured:
        directory = Path(configured).expanduser()
        if not directory.is_absolute():
            directory = project_root() / directory
        return directory.resolve()
    return project_root() / "runtime" / "experiments"


def frontend_directory() -> Path:
    return project_root() / "frontend" / "dist"


def opentrons_protocol() -> Path:
    return project_root() / "opentrons" / "SDL_CSV_protocol.py"


def resource_path(*parts: str):
    """Read packaged fixtures through importlib.resources, independently of cwd."""
    return files("sdl_color_lab.resources").joinpath(*parts)
