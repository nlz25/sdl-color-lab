"""One operator folder per experiment; implementation files stay in .state."""

from __future__ import annotations

import json
from pathlib import Path
import re

STATE_DIRECTORY = ".state"


def cache_directory(store: Path) -> Path:
    return Path(store).resolve().parent / ".cache"


def experiment_directory(records: Path) -> Path:
    records = Path(records)
    return records.parent if records.name == STATE_DIRECTORY else records


def public_id(records: Path, manifest: dict | None = None) -> str:
    records = Path(records)
    if manifest is None:
        manifest = json.loads((records / "session.json").read_text(encoding="utf-8"))
    identifier = manifest.get("public_id", records.name)
    if not isinstance(identifier, str):
        raise ValueError("实验编号无效")
    return identifier


def session_paths(store: Path):
    """Read both organised experiments and pre-existing external session folders."""
    store = Path(store)
    if not store.exists():
        return
    for folder in sorted(store.iterdir(), reverse=True):
        if not folder.is_dir() or folder.is_symlink() or folder.name.startswith("."):
            continue
        records = folder / STATE_DIRECTORY
        if records.is_symlink():
            continue
        if (records / "session.json").is_file():
            yield records
        elif (folder / "session.json").is_file():
            yield folder


def find_session(store: Path, identifier: str) -> Path | None:
    matches = []
    for records in session_paths(store):
        try:
            candidate = public_id(records)
        except (OSError, ValueError, TypeError):
            continue
        if candidate == identifier:
            matches.append(records)
    if len(matches) > 1:
        raise ValueError("存在重复实验编号，请核对实验文件夹")
    return matches[0] if matches else None


def new_session_path(
    store: Path, identifier: str, method: str, model: str, *, virtual: bool = False
) -> Path:
    label = "BO-EI" if method == "bo" else "GPT" + model[3:]
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)[:60]
    if virtual:
        label += "_virtual"
    folder = Path(store) / f"{label}_{identifier[:8]}"
    if folder.exists():
        records = folder / STATE_DIRECTORY
        if (records / "session.json").is_file() and public_id(records) == identifier:
            return records
        if not (records / "session.json").is_file():
            raise ValueError("实验文件夹初始化未完成，请核对原目录后重试")
        # A short-ID collision must never overwrite a different experiment.
        folder = Path(store) / f"{label}_{identifier}"
        if folder.exists():
            raise ValueError("实验文件夹已存在，请恢复原实验或新建实验")
    return folder / STATE_DIRECTORY
