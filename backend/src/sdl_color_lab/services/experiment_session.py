"""One fixed model and six rounds per experiment, independent of the web UI.

The existing workflow state remains the authority for decisions and measurements.
Session configuration is immutable; phase is derived from the selected run.
An OS advisory lock is released by the OS even after a process is interrupted.
"""

from __future__ import annotations

import argparse
import csv
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
from pathlib import Path

from sdl_color_lab.settings import load_environment, project_root
import re
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import uuid
import zipfile

from sdl_color_lab.services import workflow
from sdl_color_lab.core import storage
from sdl_color_lab.core.common import (
    DYE_NAMES,
    NAMES,
    TOTAL,
    validate_inputs,
    validate_rgb,
)
from sdl_color_lab.algorithms.llm_optimizer import build_messages

BUDGET = 6
DEFAULT_TARGET = [143, 150, 106]
DEFAULT_BASE_URL = "https://api.openai.com/v1"
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _public_config(config: dict) -> dict:
    model = config.get("model", "gpt-6")
    if not isinstance(model, str) or not re.fullmatch(r"gpt-[A-Za-z0-9_.-]+", model):
        raise ValueError("模型标识必须是明确的 gpt-... 名称")
    base_url = config.get("base_url", DEFAULT_BASE_URL).rstrip("/")
    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("API 地址须为不含密钥、用户名或查询参数的 HTTP(S) 地址")
    public = {"model": model, "base_url": base_url}
    receipt = config.get("preflight")
    if isinstance(receipt, dict):
        public["preflight"] = {
            key: receipt[key]
            for key in (
                "model",
                "base_url",
                "checked_at_utc",
                "model_retrievable",
                "check_method",
                "note",
            )
            if key in receipt
        }
    return public


def read_model_config() -> dict:
    """Read local credentials without returning or persisting their values."""

    load_environment()
    config = _public_config(
        {
            "model": os.getenv("OPENAI_MODEL", "gpt-6"),
            "base_url": os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
        }
    )
    config["api_key_configured"] = bool(
        os.getenv("OPENAI_API_KEY")
        and os.getenv("OPENAI_API_KEY") != "replace_with_your_key"
    )
    return config


def preflight_model(config: dict | None = None) -> dict:
    """Check connectivity/model retrieval only; never bill for a generation."""
    from openai import OpenAI

    current = read_model_config()
    config = _public_config(config or current)
    if not current["api_key_configured"]:
        raise ValueError("请先在本机 .env 中设置 OPENAI_API_KEY")
    try:
        with OpenAI(base_url=config["base_url"], timeout=20.0, max_retries=0) as client:
            check_method = "models.retrieve"
            try:
                result = client.models.retrieve(config["model"])
            except Exception as exc:
                # Some compatible providers expose /models but no /models/{id}.
                # Authentication/network failures must still surface directly.
                if getattr(exc, "status_code", None) not in (404, 405, 501):
                    raise
                result = None
            returned_id = getattr(result, "id", None)
            if returned_id != config["model"]:
                if isinstance(returned_id, str) and returned_id:
                    raise ValueError("Model identifier returned by endpoint differs")
                listed = client.models.list()
                if not isinstance(listed.data, list) or not any(
                    item.id == config["model"] for item in listed.data
                ):
                    raise ValueError("Configured model is absent from the model list")
                check_method = "models.list"
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        detail = f"{type(exc).__name__}"
        if isinstance(status, int):
            detail += f", HTTP {status}"
        raise ValueError(
            f"模型连接检查失败（{detail}）；请核对本机配置和权限"
        ) from None
    config["preflight"] = {
        "model": config["model"],
        "base_url": config["base_url"],
        "checked_at_utc": workflow._utc_now(),
        "model_retrievable": True,
        "check_method": check_method,
        "note": (
            "已通过 Models 列表核对配置的模型名称；生成接口在首次提案时验证。"
            if check_method == "models.list"
            else "已验证 Models 接口与模型访问权限；生成接口在首次提案时验证。"
        ),
    }
    return config


@contextmanager
def _session_lock(path: Path, *, create=False):
    path = Path(path).resolve()
    if create:
        path.mkdir(parents=True, exist_ok=True)
    elif not path.is_dir():
        raise ValueError("实验目录不存在")
    with _LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(str(path), threading.Lock())
    if not thread_lock.acquire(blocking=False):
        raise ValueError("当前实验正在处理另一项操作，请稍后刷新")
    stream = None
    acquired = False
    try:
        stream = (path / ".session.lock").open("a+b")
        if os.name == "nt":
            import msvcrt

            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise ValueError("另一进程正在操作此实验，请稍后刷新") from None
        else:
            import fcntl

            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("另一进程正在操作此实验，请稍后刷新") from None
        acquired = True
        yield path
    finally:
        if stream is not None:
            if acquired:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()
        thread_lock.release()


def _pid_definitely_dead(pid: int) -> bool:
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: absent PID.
        try:
            code = wintypes.DWORD()
            return (
                bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code)))
                and code.value != 259
            )
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False
    return False


def _recover_run_lock(run_dir: Path) -> None:
    """Only clear legacy lock files when their owning process is proven absent."""
    lock = run_dir / workflow.LOCK_NAME
    if not lock.exists():
        return
    original = lock.read_bytes()
    try:
        info = workflow._parse_json(original.decode("utf-8"))
        dead = _pid_definitely_dead(info["pid"])
    except (ValueError, TypeError, KeyError, UnicodeError):
        dead = False
    if not dead:
        raise ValueError("实验工作流仍被锁定；活跃或无法核实的进程锁不会自动删除")
    if lock.read_bytes() == original:
        lock.unlink()


def _run_path(path: Path, method: str) -> Path:
    return path / "runs" / method


def _initialize_run(path: Path, manifest: dict, method: str) -> dict:
    run_dir = _run_path(path, method)
    _recover_run_lock(run_dir)
    if not (run_dir / "state.json").exists():
        workflow.init_run(
            argparse.Namespace(
                run_dir=run_dir,
                run_id=f"{manifest['session_id']}-{method}",
                target_id=manifest["session_id"],
                method=method,
                repeat=1,
                target_rgb=manifest["config"]["target_rgb"],
                seed=manifest["config"]["seed"],
                budget=BUDGET,
                calibration=path / "calibration.json",
                initialization_mode=manifest["config"].get("initialization_mode", "calibrated"),
                model=manifest["config"]["model"] if method == "llm" else None,
                base_url=manifest["config"]["base_url"] if method == "llm" else None,
            )
        )
    with workflow._run_lock(run_dir):
        state = workflow._load_state(run_dir)
    expected = {
        "run_id": f"{manifest['session_id']}-{method}",
        "target_id": manifest["session_id"],
        "method": method,
        "repeat": 1,
        "budget": BUDGET,
        "target_rgb": manifest["config"]["target_rgb"],
        "seed": manifest["config"]["seed"],
        "total_volume_ul": TOTAL,
    }
    if any(state["config"].get(key) != value for key, value in expected.items()) or (
        state["calibration"]["data"] != manifest["calibration"]
    ) or (
        state["config"].get("initialization_mode", "calibrated")
        != manifest["config"].get("initialization_mode", "calibrated")
    ):
        raise ValueError("工作流初始化与固定会话配置不一致")
    if method == "llm" and any(
        state["config"].get(key) != manifest["config"][key]
        for key in ("model", "base_url")
    ):
        raise ValueError("GPT 模型或 API 地址与固定会话配置不一致")
    for decision in [
        *state["history"],
        *([state["pending"]] if state["pending"] else []),
    ]:
        expected_well = f"{'A' if method == 'llm' else 'B'}{decision['round']}"
        if decision["dest_well"] != expected_well:
            raise ValueError("已归档配方孔位与固定会话布局不一致")
    return state


def selected_method(manifest: dict, runs: dict) -> str:
    """Preserve old selections without rewriting any archived run or config."""
    method = manifest["config"].get("method", manifest.get("active_method"))
    if manifest.get("active_method", method) != method:
        raise ValueError("当前实验已固定模型，测试另一模型请新建实验")
    if method is None:
        llm = runs.get("llm")
        method = "bo" if runs.get("bo") is not None and llm is not None and len(llm["history"]) == BUDGET else "llm"
    if method not in ("llm", "bo"):
        raise ValueError("实验方法必须为 GPT 或 BO-EI")
    return method


def session_phase(runs: dict, method: str) -> str:
    run = runs.get(method)
    return "complete" if run is not None and len(run["history"]) == BUDGET else method


def _load(path: Path) -> dict:
    manifest = workflow._read_json(path / "session.json")
    if manifest["config"].get("demo"):
        raise ValueError("此会话仅保留为历史归档，请新建正式实验")
    if manifest.get("schema_version") != 1:
        raise ValueError("不支持的实验会话版本")
    expected = manifest["config_sha256"]
    if workflow._snapshot_hash(manifest["config"]) != expected:
        raise ValueError("实验配置校验失败")
    if (
        workflow._snapshot_hash(manifest["calibration"])
        != manifest["calibration_sha256"]
    ):
        raise ValueError("标定快照校验失败")
    started = manifest.get("started_methods", ["llm", *(["bo"] if manifest.get("bo_started") else [])])
    if not isinstance(started, list) or any(name not in ("llm", "bo") for name in started):
        raise ValueError("已启动方法的记录无效")
    runs = {
        method: _initialize_run(path, manifest, method)
        if method in started or (_run_path(path, method) / "state.json").exists()
        else None
        for method in ("llm", "bo")
    }
    method = selected_method(manifest, runs)
    if runs[method] is None:
        raise ValueError("当前方法尚未初始化")
    phase = session_phase(runs, method)
    staged = None
    if runs[method]["pending"] is not None:
        pending = runs[method]["pending"]
        prepared = path / "measurements" / method / f"{pending['round']:03d}.json"
        if prepared.exists():
            staged = workflow._read_json(prepared)
            workflow._check_metadata(staged, pending)
    return {
        **manifest,
        "path": str(path),
        "phase": phase,
        "active_method": method,
        "started_methods": [name for name, run in runs.items() if run is not None],
        "runs": runs,
        "staged_measurement": staged,
    }


def load_session(path) -> dict:
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        snapshot["opentrons_files"] = {
            method: _save_operator_recipe(directory, snapshot, _decorate(snapshot, run["pending"]))
            for method, run in snapshot["runs"].items()
            if run is not None and run["pending"] is not None
        }
        _save_results_table(directory, snapshot)
        return snapshot


def _verified_spectrum(spectrum: dict, raw: bytes, filename: str) -> dict:
    from sdl_color_lab.spectra.spectrum_import import extract_spectrum

    # Never trust client-provided RGB or arrays without re-reading the source cells.
    actual = extract_spectrum(raw, filename, spectrum["mapping"], spectrum["well"])
    for key in ("well", "source_sha256", "spectrum_sha256", "sheet", "block_id"):
        if actual.get(key) != spectrum.get(key):
            raise ValueError(f"光谱来源校验失败：{key}")
    if actual["color"] != spectrum["color"]:
        raise ValueError("颜色结果与原始光谱不一致")
    return actual


def _immutable_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("已有归档文件与当前内容冲突")
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _archive_source(path: Path, spectrum: dict, raw: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        raise ValueError("仅支持 CSV、XLSX 和 XLS 原始文件")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != spectrum["source_sha256"]:
        raise ValueError("上传文件哈希与解析结果不一致")
    relative = Path("sources") / f"{digest}{suffix}"
    _immutable_bytes(path / relative, raw)
    return relative.as_posix()


def _calibration_rows(calibrations: dict) -> list[dict]:
    if set(calibrations) not in (set(DYE_NAMES), set(NAMES)):
        raise ValueError("需要红、绿、蓝各一份现场标定；兼容已有的实测纯水标定")
    return [
        {
            "name": name,
            "recipe": {reagent: TOTAL if reagent == name else 0 for reagent in NAMES},
            "rgb": calibrations[name]["spectrum"]["color"]["rgb"],
        }
        for name in NAMES
        if name in calibrations
    ]


def build_prompt(
    calibrations, target_rgb=None, history=None, *, initialization_mode=None
) -> list[dict]:
    rows = (
        (_calibration_rows(calibrations) if calibrations else [])
        if isinstance(calibrations, dict)
        else calibrations
    )
    state = {
        "target_rgb": list(target_rgb or DEFAULT_TARGET),
        "budget": BUDGET,
        "seed": 0,
        "history": history or [],
        "initialization_mode": initialization_mode or (
            "cold_start" if not rows else "calibrated"
        ),
    }
    validate_inputs(state, rows, allow_exhausted=True)
    return build_messages(state, rows)


def create_session(
    path,
    *,
    calibrations: dict | None = None,
    target_rgb=None,
    plate_id: str,
    blank_corrected: bool | None,
    config: dict | None = None,
    seed: int = 0,
    initial_method: str = "llm",
    public_id: str | None = None,
) -> dict:
    if initial_method not in ("llm", "bo"):
        raise ValueError("实验方法必须为 GPT 或 BO-EI")
    if calibrations:
        raise ValueError("新实验不使用基色标定，请直接设置目标颜色后开始")
    if blank_corrected is False:
        raise ValueError("请先确认仪器已按转换脚本要求处理纯水与孔板背景")
    if blank_corrected is not None and type(blank_corrected) is not bool:
        raise ValueError("背景处理状态必须为布尔值或未知")
    if not isinstance(plate_id, str) or not plate_id.strip():
        raise ValueError("请登记板号")
    target_rgb = list(target_rgb or DEFAULT_TARGET)
    validate_rgb(target_rgb)
    public = _public_config(config or read_model_config())
    if initial_method == "llm":
        receipt = public.get("preflight", {})
        if not (
            receipt.get("model_retrievable") is True
            and all(receipt.get(key) == public[key] for key in ("model", "base_url"))
        ):
            raise ValueError("请先对所选模型和 API 地址完成连接检查")
        workflow._parse_time(receipt["checked_at_utc"], "preflight.checked_at_utc")
    # An explicit empty snapshot keeps old archive/state contracts without
    # silently falling back to measured dyes.
    rows = []
    fixed_config = {
        **public,
        "target_rgb": target_rgb,
        "plate_id": plate_id.strip(),
        "seed": seed,
        "budget": BUDGET,
        "method": initial_method,
        "total_volume_ul": TOTAL,
        "blank_corrected": blank_corrected,
        "scoring": workflow.SCORING,
        "initialization_mode": "cold_start",
    }
    validate_inputs({**fixed_config, "history": []}, rows)
    with _session_lock(Path(path), create=True) as directory:
        if any(item.name != ".session.lock" for item in directory.iterdir()):
            raise ValueError("实验目录非空；请选择新目录或恢复已有实验")
        manifest = {
            "schema_version": 1,
            "session_id": uuid.uuid4().hex,
            "created_at_utc": workflow._utc_now(),
            "config": fixed_config,
            "config_sha256": workflow._snapshot_hash(fixed_config),
            "calibration": rows,
            "calibration_sha256": workflow._snapshot_hash(rows),
            "calibration_sources": {},
            "bo_started": initial_method == "bo",
            "active_method": initial_method,
            "started_methods": [initial_method],
        }
        if public_id is not None:
            manifest["public_id"] = public_id
        workflow._atomic_write(
            directory / "calibration.json", workflow._json_text(rows)
        )
        workflow._atomic_write(
            directory / "session.json", workflow._json_text(manifest)
        )
        return _load(directory)


def _require_method(snapshot: dict, expected_method: str | None = None) -> str:
    method = snapshot["active_method"]
    if expected_method is not None and expected_method != method:
        raise ValueError("当前实验已固定模型，测试另一模型请新建实验")
    return method


def _active(snapshot: dict, expected_method: str | None = None) -> tuple[str, dict]:
    method = _require_method(snapshot, expected_method)
    state = snapshot["runs"][method]
    if len(state["history"]) == BUDGET:
        raise ValueError("当前实验六轮已完成，不能生成第七轮；测试另一模型请新建实验")
    return method, state


def _decorate(snapshot: dict, pending: dict) -> dict:
    return {
        **pending,
        "execution_index": pending["round"]
        + (BUDGET if pending["method"] == "bo" else 0),
        "plate_id": snapshot["config"]["plate_id"],
    }


def _robot_text(decision: dict) -> str:
    from sdl_color_lab.opentrons.csv_export import export_recipe_csv

    return export_recipe_csv(decision, decision["execution_index"])


def _save_operator_recipe(directory: Path, snapshot: dict, decision: dict) -> dict:
    from sdl_color_lab.opentrons.csv_export import recipe_csv_filename

    folder = (
        storage.experiment_directory(directory) / "opentrons"
        if directory.name == storage.STATE_DIRECTORY
        else directory.parent.parent / "opentrons" / directory.name
    )
    filename = recipe_csv_filename(
        decision, snapshot["config"]["model"]
    )
    if snapshot.get("validation", {}).get("measurement_source") == "synthetic":
        filename = "VIRTUAL_" + filename
    path = folder / filename
    _immutable_bytes(path, _robot_text(decision).encode("utf-8"))
    try:
        display_folder = folder.relative_to(project_root()).as_posix()
    except ValueError:
        display_folder = str(folder)
    return {
        "filename": filename,
        "path": str(path),
        "directory": str(folder),
        "display_directory": display_folder,
    }


def _save_results_table(directory: Path, snapshot: dict) -> None:
    if directory.name != storage.STATE_DIRECTORY:
        return
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow([
        "model", "round", "well", "status", "red_ul", "green_ul", "blue_ul",
        "water_ul", "rgb_r", "rgb_g", "rgb_b", "delta_e_2000", "completed_at_utc",
    ])
    for method, run in snapshot["runs"].items():
        if run is None:
            continue
        model = "BO-EI" if method == "bo" else snapshot["config"]["model"]
        for row in [*run["history"], *([run["pending"]] if run["pending"] else [])]:
            rgb = row.get("rgb", ["", "", ""])
            writer.writerow([
                model, row["round"], row["dest_well"],
                "measured" if "rgb" in row else "pending",
                *(row["recipe"][name] for name in ("Red", "Green", "Blue", "water")),
                *rgb, row.get("delta_e_2000", ""), row.get("completed_at_utc", ""),
            ])
    path = storage.experiment_directory(directory) / "results.csv"
    content = stream.getvalue()
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        workflow._atomic_write(path, content)


def propose_current(path, *, method=None, round_number=None) -> dict:
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        method, state = _active(snapshot, method)
        expected_round = state["pending"]["round"] if state["pending"] else len(state["history"]) + 1
        if round_number is not None and round_number != expected_round:
            raise ValueError("当前轮次已推进，请刷新后重试")
        round_number = (
            state["pending"]["round"] if state["pending"] else len(state["history"]) + 1
        )
        well = f"{'A' if method == 'llm' else 'B'}{round_number}"
        pending = workflow.propose_run(
            _run_path(directory, method), well
        )
        decision = _decorate(snapshot, pending)
        destination = (
            directory / "robot" / f"{decision['execution_index']:02d}-{well}.csv"
        )
        _immutable_bytes(destination, _robot_text(decision).encode("utf-8"))
        _save_operator_recipe(directory, snapshot, decision)
        return decision


def _invalid_response(path: Path, snapshot: dict) -> Path | None:
    if snapshot["active_method"] != "llm" or snapshot["runs"]["llm"]["pending"] is not None:
        return None
    number = len(snapshot["runs"]["llm"]["history"]) + 1
    if number > BUDGET:
        return None
    response = _run_path(path, "llm") / "llm_responses" / f"{number:03d}.txt"
    if not response.exists():
        return None
    from sdl_color_lab.algorithms.llm_optimizer import parse_response

    try:
        raw = response.read_bytes().decode("utf-8")
        workflow._parse_json(raw)
        parse_response(raw)
    except (ValueError, UnicodeError):
        return response
    return None


def invalid_response_pending(path) -> bool:
    with _session_lock(Path(path)) as directory:
        return _invalid_response(directory, _load(directory)) is not None


def retry_invalid_response(path, *, method=None, round_number=None) -> dict:
    """Explicitly archive an invalid saved reply; never make an API call here."""
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        _, state = _active(snapshot, method)
        if round_number is not None and round_number != len(state["history"]) + 1:
            raise ValueError("当前轮次已推进，请刷新后重试")
        response = _invalid_response(directory, snapshot)
        if response is None:
            raise ValueError("当前没有可重试的无效回复；有效回复和待执行配方受到保护")
        raw = response.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        archived = response.parent / "rejected" / f"{response.stem}-{digest}.txt"
        _immutable_bytes(archived, raw)
        response.unlink()
        return _load(directory)


def robot_download(path, *, method=None, round_number=None) -> dict[str, str]:
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        method = _require_method(snapshot, method)
        state = snapshot["runs"][method]
        if state["pending"] is None:
            raise ValueError("当前没有待执行配方")
        if round_number is not None and round_number != state["pending"]["round"]:
            raise ValueError("当前轮次已推进，请刷新后重新下载配方")
        decision = _decorate(snapshot, state["pending"])
        text = _robot_text(decision)
        return {
            "content": text,
            **_save_operator_recipe(directory, snapshot, decision),
        }


def robot_csv(path, *, method=None, round_number=None) -> str:
    return robot_download(path, method=method, round_number=round_number)["content"]


def open_robot_folder(path, *, method=None, round_number=None) -> dict[str, str]:
    download = robot_download(path, method=method, round_number=round_number)
    folder = download["directory"]
    try:
        if sys.platform == "win32":
            os.startfile(folder)
        else:
            command = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.run([command, folder], check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise ValueError(f"无法自动打开 CSV 文件夹，请手动打开：{folder}") from None
    return {"directory": folder}


def _measurement_identity(spectrum: dict) -> dict:
    return {
        key: spectrum.get(key)
        for key in (
            "source_sha256",
            "spectrum_sha256",
            "sheet",
            "block_id",
            "well",
            "mapping",
        )
    }


def record_current(
    path,
    spectrum: dict,
    raw: bytes,
    filename: str,
    completed_at: str | None = None,
    *,
    method: str | None = None,
    round_number: int | None = None,
) -> dict:
    actual = _verified_spectrum(spectrum, raw, filename)
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        if method is None:
            method, state = _active(snapshot)
        else:
            method = _require_method(snapshot, method)
            state = snapshot["runs"][method]
        pending = state["pending"]
        if round_number is None:
            if pending is None:
                raise ValueError("当前没有待测配方；重传须指定原模型和轮次")
            round_number = pending["round"]
        if type(round_number) is not int or not 1 <= round_number <= BUDGET:
            raise ValueError("轮次必须是 1–6 的整数")
        previous = (
            state["history"][round_number - 1]
            if round_number <= len(state["history"])
            else None
        )
        decision = previous or pending
        if decision is None or decision["round"] != round_number:
            raise ValueError("测量不属于当前待测轮次")
        if actual["well"] != decision["dest_well"]:
            raise ValueError(f"必须上传当前孔 {decision['dest_well']} 的光谱")
        identity = _measurement_identity(actual)
        output = directory / "measurements" / method / f"{round_number:03d}.json"
        archived = workflow._read_json(output) if output.exists() else None
        # A single-spectrum CSV contains no acquisition time. Record its feedback
        # submission time explicitly, without claiming it was measured then.
        # Retries must reuse the persisted event, including after a partial write.
        supplied_time = (
            completed_at if completed_at is not None else actual.get("acquired_at")
        )
        if supplied_time is not None:
            acquired = workflow._parse_time(supplied_time, "实际测量时间")
            time_source = "instrument" if actual.get("acquired_at") else "operator"
        elif previous is not None or archived is not None:
            saved_measurement = previous["measurement"] if previous else archived
            acquired = workflow._parse_time(
                saved_measurement["completed_at_utc"], "归档反馈时间"
            )
            time_source = saved_measurement.get("provenance", {}).get(
                "time_source", "legacy_measurement"
            )
        else:
            acquired = datetime.now(timezone.utc)
            time_source = "feedback_submission"
        if previous is not None:
            if previous["measurement"]["provenance"]["extraction"] != identity:
                raise ValueError("已完成轮次存在不同测量，不能覆盖")
            original_time = workflow._parse_time(
                previous["measurement"]["completed_at_utc"], "归档测量时间"
            )
            if acquired != original_time:
                raise ValueError("重复上传的测量时间与已归档记录不同，不能覆盖")
            return {**_summary(snapshot), "record_result": "already_recorded"}
        created = workflow._parse_time(decision["created_at_utc"], "配方生成时间")
        if acquired < created:
            raise ValueError("实际测量时间早于本轮配方，不能录入旧扫描")
        if acquired > datetime.now(timezone.utc) + timedelta(seconds=5):
            raise ValueError("实际测量时间不能在未来")
        if (
            actual.get("acquired_at")
            and workflow._parse_time(actual["acquired_at"], "仪器测量时间") != acquired
        ):
            raise ValueError("填写时间与仪器扫描时间不一致")
        if archived is not None:
            measurement = archived
            workflow._check_metadata(measurement, decision)
            if measurement["provenance"]["extraction"] != identity:
                raise ValueError("该轮已有待提交测量归档，不能用其他扫描覆盖")
            if (
                workflow._parse_time(measurement["completed_at_utc"], "归档测量时间")
                != acquired
            ):
                raise ValueError("重试的测量时间与已有归档不同，请使用原测量时间")
        else:
            copy = _archive_source(directory, actual, raw, filename)
            measurement = {key: decision[key] for key in workflow.METADATA}
            measurement.update(
                {
                    "rgb": actual["color"]["rgb"],
                    "completed_at_utc": acquired.isoformat().replace("+00:00", "Z"),
                    "provenance": {
                        "kind": (
                            "blank_corrected_absorbance"
                            if snapshot["config"]["blank_corrected"] is True
                            else "absorbance_as_provided"
                        ),
                        "blank_corrected": snapshot["config"]["blank_corrected"],
                        "time_source": time_source,
                        "measured_at_utc": (
                            None
                            if time_source == "feedback_submission"
                            else acquired.isoformat().replace("+00:00", "Z")
                        ),
                        "source_copy": copy,
                        "filename": Path(filename).name,
                        "sha256": actual["source_sha256"],
                        "prepared_at_utc": workflow._utc_now(),
                        "conversion": "D65/CIE1931-2deg/transmission-to-sRGB",
                        "source_color": actual["color"],
                        "extraction": identity,
                        "spectrum": actual,
                        "plate_id": snapshot["config"]["plate_id"],
                    },
                }
            )
            workflow._atomic_write(output, workflow._json_text(measurement))
        result = workflow.record_run(_run_path(directory, method), output)
        return {**_summary(_load(directory)), "record_result": result["record_result"]}


def select_method(path, method: str) -> dict:
    """Accept old clients' retries only for this experiment's fixed method."""
    if method not in ("llm", "bo"):
        raise ValueError("实验方法必须为 GPT 或 BO-EI")
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        _require_method(snapshot, method)
        return snapshot


def start_bo(path) -> dict:
    """Compatibility alias; it cannot change a session's fixed method."""
    return select_method(path, "bo")


def _summary(snapshot: dict) -> dict:
    result = {
        "session_id": snapshot["session_id"],
        "phase": snapshot["phase"],
        "active_method": snapshot["active_method"],
        "config": snapshot["config"],
        "methods": {},
        "completed_rounds": len(snapshot["runs"][snapshot["active_method"]]["history"]),
        "total_rounds": BUDGET,
        "history": [],
        "pending": None,
        "pendings": {},
    }
    for method, run in snapshot["runs"].items():
        if run is None:
            continue
        result["methods"][method] = workflow.summarize(run)
        result["history"].extend(
            _decorate(snapshot, record) for record in run["history"]
        )
        if run["pending"] is not None:
            result["pendings"][method] = _decorate(snapshot, run["pending"])
    result["pending"] = result["pendings"].get(snapshot["active_method"])
    return result


def session_summary(path) -> dict:
    with _session_lock(Path(path)) as directory:
        return _summary(_load(directory))


def archive_export(path) -> bytes:
    """Export only experiment artifacts; local API configuration is never copied."""
    with _session_lock(Path(path)) as directory:
        snapshot = _load(directory)
        _save_results_table(directory, snapshot)
        for method, run in snapshot["runs"].items():
            if run is not None:
                with workflow._run_lock(_run_path(directory, method)):
                    workflow.export_run(_run_path(directory, method), run)
        workflow._atomic_write(
            directory / "summary.json", workflow._json_text(_summary(snapshot))
        )
        stream = io.BytesIO()
        roots = {"sources", "runs", "measurements", "robot", "validation"}
        files = {"session.json", "calibration.json", "summary.json"}
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if directory.name == storage.STATE_DIRECTORY:
                archive.write(storage.experiment_directory(directory) / "results.csv", "results.csv")
            for item in sorted(directory.rglob("*")):
                relative = item.relative_to(directory)
                if (
                    item.is_file()
                    and not item.is_symlink()
                    and not any(part.startswith(".") for part in relative.parts)
                    and (relative.parts[0] in roots or relative.as_posix() in files)
                ):
                    archive.write(item, relative.as_posix())
        return stream.getvalue()
