"""Local HTTP boundary for the React operator console.

The experiment workflow remains the authority for proposals and measurements.
Only opaque upload/session identifiers cross this boundary; credentials stay local.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import wraps
import hashlib
import logging
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response

# Uvicorn imports this module on its main thread. On macOS, first importing
# PyTorch in a disposable AnyIO worker can crash when that worker is destroyed.
# Initialize its native runtime before any request enters the worker pool.
from sdl_color_lab.algorithms import bo_optimizer  # noqa: F401
from sdl_color_lab.services import experiment_session as sessions
from sdl_color_lab.core.common import delta_e
from sdl_color_lab.core import storage
from sdl_color_lab.spectra import spectrum_import
from sdl_color_lab.services import workflow
from sdl_color_lab import settings
from sdl_color_lab.api.schemas import (
    SpectrumSelection,
    SessionCreation,
    Measurement,
    ImportProfile,
    MethodSelection,
    MethodAction,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}\Z")
UPLOAD_ID = re.compile(r"[a-f0-9]{64}\Z")
LOGGER = logging.getLogger(__name__)


def _error_text(exc: Exception) -> str:
    text = str(exc)
    secret = os.getenv("OPENAI_API_KEY")
    if secret:
        text = text.replace(secret, "[已隐藏]")
    # Keep the established Chinese parsing/workflow errors, prefix English ones.
    if not re.search(r"[\u4e00-\u9fff]", text):
        text = f"操作未完成，请核对输入：{text}"
    return text[:1500]


def _origin_tuple(value: str) -> tuple[str, str, int] | None:
    """Parse one serialized HTTP origin, without URL paths or credentials."""
    if not value or any(
        character.isspace()
        or ord(character) < 32
        or ord(character) == 127
        or character in ",?#"
        for character in value
    ):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        host = parsed.hostname.lower()
        port = parsed.port
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        if parsed.netloc.lower() != authority:
            return None
        return (
            parsed.scheme,
            host,
            port if port is not None else (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


def _same_origin_with_portless_header(
    origins: list[str], referers: list[str], fetch_site: str | None,
    expected: tuple[str, str, int],
) -> bool:
    """Handle browsers/extensions omitting only Origin's non-default port.

    A genuinely different origin still fails: both the browser's Fetch Metadata
    and the full Referer must independently identify the exact local origin.
    """
    if len(origins) != 1 or len(referers) != 1 or fetch_site != "same-origin":
        return False
    origin = _origin_tuple(origins[0])
    if origin is None or origin[:2] != expected[:2]:
        return False
    if urlsplit(origins[0]).port is not None:
        return False
    referer = referers[0]
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in referer):
        return False
    try:
        parsed = urlsplit(referer)
        if parsed.fragment or parsed.username is not None or parsed.password is not None:
            return False
        return _origin_tuple(f"{parsed.scheme}://{parsed.netloc}") == expected
    except ValueError:
        return False


def create_app(data_dir: str | Path | None = None, dist_dir: str | Path | None = None):
    app = FastAPI(title="配色实验", docs_url=None, redoc_url=None, openapi_url=None)
    public_url = settings.public_origin()
    public_origin = _origin_tuple(public_url) if public_url else None
    if public_url and public_origin is None:
        raise ValueError("COLOR_LAB_PUBLIC_ORIGIN must be a single http(s) origin without a path")
    desktop_files = public_origin is None
    store = Path(data_dir or settings.session_directory()).resolve()
    cache_root = storage.cache_directory(store)
    upload_root = cache_root / "uploads"
    request_root = cache_root / "requests"
    dist = Path(dist_dir or settings.frontend_directory()).resolve()
    preflights: dict[str, dict] = {}
    app.state.data_dir = store

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # Host validation also prevents DNS rebinding to this loopback service.
        try:
            host = request.url.hostname
            port = request.url.port
        except ValueError:
            host, port = None, None
        request_origin = (
            request.url.scheme, host,
            port if port is not None else (443 if request.url.scheme == "https" else 80),
        )
        if host not in {"localhost", "127.0.0.1", "::1"} and request_origin != public_origin:
            return JSONResponse({"detail": "仅允许通过本机地址访问"}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            port = (
                port
                if port is not None
                else (443 if request.url.scheme == "https" else 80)
            )
            display_host = f"[{host}]" if ":" in host else host
            local_url = f"{request.url.scheme}://{display_host}:{port}/"
            origins = request.headers.getlist("origin")
            if origins:
                origin = _origin_tuple(origins[0]) if len(origins) == 1 else None
                expected = (request.url.scheme, host, port)
                if origin != expected and not _same_origin_with_portless_header(
                    origins, request.headers.getlist("referer"),
                    request.headers.get("sec-fetch-site"), expected,
                ):
                    return JSONResponse(
                        {
                            "detail": (
                                "页面来源与本地服务不一致，请通过 "
                                f"{local_url} 重新打开页面后重试"
                            )
                        },
                        status_code=403,
                    )
            elif request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {
                        "detail": (
                            "请求缺少页面来源，无法确认是本地操作。请通过 "
                            f"{local_url} 重新打开页面后重试"
                        )
                    },
                    status_code=403,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_body(request, exc):
        fields = ", ".join(
            ".".join(str(part) for part in error["loc"] if part != "body")
            for error in exc.errors()
        )
        return JSONResponse(
            {"detail": f"请求格式有误，请检查：{fields}"}, status_code=422
        )

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({"detail": _error_text(exc)}, status_code=400)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        # Do not return request bodies, filesystem traces or provider errors.
        LOGGER.error("Local API request failed: %s", type(exc).__name__)
        return JSONResponse(
            {"detail": "操作未完成；实验记录已保留，请刷新后重试"}, status_code=500
        )

    def session_path(identifier: str) -> Path:
        if not SAFE_ID.fullmatch(identifier):
            raise HTTPException(404, "实验不存在")
        path = storage.find_session(store, identifier)
        if path is None:
            raise HTTPException(404, "实验不存在")
        if workflow._read_json(path / "session.json")["config"].get("demo"):
            raise HTTPException(410, "此会话仅保留为历史归档，请新建正式实验")
        return path

    def snapshot(path: Path) -> dict:
        result = sessions.load_session(path)
        summary = sessions._summary(result)
        return {
            **result,
            "id": storage.public_id(path, result),
            "summary": summary,
            "pending": summary["pending"],
            "invalid_response_pending": sessions.invalid_response_pending(path),
        }

    def profiles() -> dict:
        file = cache_root / "import_profiles.json"
        if not file.exists():
            file = store / "import_profiles.json"
        return workflow._read_json(file) if file.exists() else {}

    def serialize_operation(operation):
        @wraps(operation)
        def guarded(identifier: str, *args, **kwargs):
            session_path(identifier)
            with sessions._session_lock(
                request_root / f"operation-{identifier}", create=True
            ):
                return operation(identifier, *args, **kwargs)

        return guarded

    def upload_files(identifier: str) -> tuple[bytes, str]:
        if not UPLOAD_ID.fullmatch(identifier):
            raise HTTPException(404, "上传文件不存在")
        directory = upload_root / identifier
        if not directory.exists():
            directory = store.parent / "web_uploads" / identifier
        if directory.is_symlink() or not (directory / "metadata.json").is_file():
            raise HTTPException(404, "上传文件不存在")
        metadata = workflow._read_json(directory / "metadata.json")
        raw = (directory / "source").read_bytes()
        if hashlib.sha256(raw).hexdigest() != metadata["source_sha256"]:
            raise ValueError("上传归档校验失败，请重新上传原始文件")
        return raw, metadata["filename"]

    def upload_descriptor(identifier: str, raw: bytes, filename: str) -> dict:
        sheets = spectrum_import.load_workbook_data(raw, filename)
        return {
            "upload_id": identifier,
            "filename": filename,
            "blocks": spectrum_import.discover_blocks(sheets),
            "preview": {
                sheet: [row[:30] for row in rows[:30]] for sheet, rows in sheets.items()
            },
            "dimensions": {
                sheet: {
                    "rows": len(rows),
                    "columns": max((len(row) for row in rows), default=0),
                }
                for sheet, rows in sheets.items()
            },
        }

    def save_upload(raw: bytes, filename: str) -> dict:
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1][:200]
        if Path(filename).suffix.lower() not in {".csv", ".xls", ".xlsx"}:
            raise ValueError("仅支持原始 Excel（.xls、.xlsx）或两列 CSV")
        if not raw:
            raise ValueError("上传文件为空")
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "文件超过 25 MB，请上传较小的测量工作簿")
        identifier = hashlib.sha256(filename.encode() + b"\0" + raw).hexdigest()
        descriptor = upload_descriptor(identifier, raw, filename)
        directory = upload_root / identifier
        sessions._immutable_bytes(directory / "source", raw)
        sessions._immutable_bytes(
            directory / "metadata.json",
            workflow._json_text(
                {
                    "filename": filename,
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                }
            ).encode(),
        )
        return descriptor

    def extract(identifier: str, block: dict, well: str, expected_well=None):
        raw, filename = upload_files(identifier)
        parsed = spectrum_import.extract_spectrum(
            raw, filename, block, well, expected_well=expected_well
        )
        return {"spectrum": parsed, "raw": raw, "filename": filename}

    @app.get("/api/bootstrap")
    def bootstrap():
        records = []
        if store.exists():
            for path in storage.session_paths(store):
                try:
                    # Dropdown metadata is advisory. Read the atomically written
                    # files without taking the active session's mutation lock.
                    item = workflow._read_json(path / "session.json")
                    if item["config"].get("demo"):
                        continue
                    runs = {
                        method: workflow._read_json(path / f"runs/{method}/state.json")
                        if (path / f"runs/{method}/state.json").exists() else None
                        for method in ("llm", "bo")
                    }
                    active = sessions.selected_method(item, runs)
                    phase = sessions.session_phase(runs, active)
                    identifier = storage.public_id(path, item)
                except (ValueError, OSError, KeyError):
                    continue
                records.append(
                    {
                        "id": identifier,
                        "plate_id": item["config"]["plate_id"],
                        "phase": phase,
                        "active_method": active,
                        "model": item["config"].get("model", "gpt-6"),
                    }
                )
        try:
            model_config = sessions.read_model_config()
        except ValueError as exc:
            model_config = {
                "model": "gpt-6",
                "base_url": "",
                "api_key_configured": False,
                "error": _error_text(exc),
            }
        return {
            "sessions": records,
            "model_config": model_config,
            "import_profiles": profiles(),
            "default_target": sessions.DEFAULT_TARGET,
            "initialization_mode": "cold_start",
            "capabilities": {"open_local_folder": desktop_files},
        }

    @app.post("/api/preflight")
    def preflight():
        config = sessions.preflight_model()
        token = secrets.token_urlsafe(32)
        preflights[token] = config
        return {"token": token, "config": config}

    @app.post("/api/uploads")
    async def upload(file: UploadFile = File(...)):
        try:
            raw = await file.read(MAX_UPLOAD_BYTES + 1)
            return save_upload(raw, file.filename or "")
        finally:
            await file.close()

    @app.post("/api/uploads/{identifier}/spectrum")
    def spectrum(identifier: str, body: SpectrumSelection):
        parsed = extract(identifier, body.block, body.well, body.expected_well)[
            "spectrum"
        ]
        if body.target_rgb is not None:
            from sdl_color_lab.core.common import validate_rgb

            validate_rgb(body.target_rgb)
            parsed["delta_e_2000"] = delta_e(parsed["color"]["rgb"], body.target_rgb)
        return parsed

    @app.get("/api/uploads/{identifier}/preview")
    def preview(
        identifier: str,
        sheet: str,
        row: int = 0,
        column: int = 0,
        rows: int = 30,
        columns: int = 30,
    ):
        raw, filename = upload_files(identifier)
        sheets = spectrum_import.load_workbook_data(raw, filename)
        if sheet not in sheets or min(row, column) < 0:
            raise ValueError("工作表或预览位置无效")
        if not 1 <= rows <= 100 or not 1 <= columns <= 50:
            raise ValueError("预览最多显示 100 行、50 列")
        return {
            "sheet": sheet,
            "row": row,
            "column": column,
            "cells": [
                values[column : column + columns]
                for values in sheets[sheet][row : row + rows]
            ],
        }

    @app.post("/api/import-profiles")
    def save_profile(body: ImportProfile):
        name = body.name.strip()
        if not name:
            raise ValueError("请填写映射名称")
        allowed = {
            "sheet",
            "orientation",
            "header_row",
            "first_data_row",
            "last_data_row",
            "first_data_col",
            "last_data_col",
            "axis_index",
        }
        mapping = {key: value for key, value in body.mapping.items() if key in allowed}
        if mapping.get("orientation") not in {"csv", "wells_rows", "wells_columns"}:
            raise ValueError("映射方向无效")
        if mapping["orientation"] != "csv" and set(mapping) != allowed:
            raise ValueError("映射缺少工作表或数据区域坐标")
        # A profile is only a preference: every extraction revalidates its cells.
        with sessions._session_lock(cache_root, create=True):
            current = profiles()
            current[name] = mapping
            workflow._atomic_write(
                cache_root / "import_profiles.json", workflow._json_text(current)
            )
        return current

    @app.post("/api/sessions")
    def create_session(body: SessionCreation):
        identifier = str(body.request_id)
        identity = body.model_dump(mode="json", exclude={"preflight_token"})
        # Match creation receipts written before the retired mode was removed.
        identity["demo"] = False
        # Keep old GPT-first creation receipts idempotent after adding selection.
        if identity["initial_method"] == "llm":
            identity.pop("initial_method")
        fingerprint = workflow._snapshot_hash(identity)
        # Serialize request reservations across threads and local server processes.
        with sessions._session_lock(request_root, create=True):
            journal = request_root / f"{identifier}.json"
            path = storage.find_session(store, identifier)
            previous_journal = journal
            if not previous_journal.exists():
                previous_journal = store.parent / "web_requests" / journal.name
            if previous_journal.exists():
                saved = workflow._read_json(previous_journal)
                if saved["fingerprint"] != fingerprint:
                    raise HTTPException(409, "此初始化请求已绑定其他设置，请新建实验")
                if path is not None:
                    return snapshot(path)
            if body.calibrations:
                raise ValueError("新实验不使用基色标定，请直接设置目标颜色后开始")
            if body.initial_method == "llm":
                config = preflights.get(body.preflight_token or "")
                if config is None:
                    raise ValueError("请先完成模型连接检查；重启服务后需重新检查")
            else:
                config = sessions.read_model_config()
            if path is None:
                path = storage.new_session_path(
                    store, identifier, body.initial_method, config["model"]
                )
            workflow._atomic_write(
                journal, workflow._json_text({"fingerprint": fingerprint})
            )
            sessions.create_session(
                path,
                target_rgb=body.target_rgb,
                plate_id=body.plate_id or f"EXP-{identifier[:8].upper()}",
                blank_corrected=body.blank_confirmed,
                config=config,
                initial_method=body.initial_method,
                public_id=identifier,
            )
            return snapshot(path)

    @app.get("/api/sessions/{identifier}")
    def get_session(identifier: str):
        return snapshot(session_path(identifier))

    @app.post("/api/sessions/{identifier}/propose")
    @serialize_operation
    def propose(identifier: str, body: MethodAction | None = None):
        path = session_path(identifier)
        sessions.propose_current(
            path, method=body.method if body else None,
            round_number=body.round_number if body else None,
        )
        return snapshot(path)

    @app.post("/api/sessions/{identifier}/record")
    @serialize_operation
    def record(identifier: str, body: Measurement):
        path = session_path(identifier)
        selected = extract(body.upload_id, body.block, body.well)
        result = sessions.record_current(
            path,
            **selected,
            completed_at=body.completed_at,
            method=body.method,
            round_number=body.round_number,
        )
        return {**snapshot(path), "record_result": result["record_result"]}

    @app.post("/api/sessions/{identifier}/start-bo")
    @serialize_operation
    def start_bo(identifier: str):
        path = session_path(identifier)
        sessions.start_bo(path)
        return snapshot(path)

    @app.post("/api/sessions/{identifier}/select-method")
    @serialize_operation
    def select_method(identifier: str, body: MethodSelection):
        path = session_path(identifier)
        sessions.select_method(path, body.method)
        return snapshot(path)

    @app.post("/api/sessions/{identifier}/retry-invalid")
    @serialize_operation
    def retry_invalid(identifier: str, body: MethodAction | None = None):
        path = session_path(identifier)
        sessions.retry_invalid_response(
            path, method=body.method if body else None,
            round_number=body.round_number if body else None,
        )
        return snapshot(path)

    @app.get("/api/opentrons/protocol.py")
    def opentrons_protocol():
        path = settings.opentrons_protocol()
        if not path.is_file():
            raise HTTPException(404, "Opentrons 协议文件不存在，请使用完整项目")
        return FileResponse(
            path,
            media_type="text/x-python",
            filename="SDL_CSV_protocol.py",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/sessions/{identifier}/opentrons/open-folder")
    @serialize_operation
    def open_opentrons_folder(identifier: str, body: MethodAction):
        if not desktop_files:
            raise HTTPException(403, "Folder access is unavailable on the server. Download the CSV instead.")
        return sessions.open_robot_folder(
            session_path(identifier), method=body.method, round_number=body.round_number
        )

    @app.get("/api/sessions/{identifier}/robot.csv")
    def robot_csv(identifier: str, method: str | None = None, round_number: int | None = None):
        download = sessions.robot_download(session_path(identifier), method=method, round_number=round_number)
        return Response(
            download["content"],
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{download["filename"]}"'},
        )

    @app.get("/api/sessions/{identifier}/archive.zip")
    def archive(identifier: str):
        raw = sessions.archive_export(session_path(identifier))
        return Response(
            raw,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="experiment.zip"'},
        )

    @app.get("/api/sessions/{identifier}/prompt")
    def prompt(identifier: str):
        current = sessions.load_session(session_path(identifier))
        return {
            "messages": sessions.build_prompt(
                current["calibration"],
                current["config"]["target_rgb"],
                current["runs"]["llm"]["history"] if current["runs"]["llm"] else [],
                initialization_mode=current["config"].get("initialization_mode", "calibrated"),
            )
        }

    @app.get("/api/health")
    def health():
        return {
            "app": "color-mixing",
            "project_root": str(settings.project_root()),
            "status": "ok",
            "time": datetime.now(timezone.utc).isoformat(),
        }

    @app.api_route(
        "/api/{unmatched:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    )
    @app.api_route(
        "/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
    )
    def missing_api(unmatched: str = ""):
        raise HTTPException(404, "接口不存在")

    @app.get("/{asset:path}")
    def frontend(asset: str):
        if asset == "api" or asset.startswith("api/"):
            raise HTTPException(404, "接口不存在")
        requested = (dist / asset).resolve()
        if not requested.is_relative_to(dist):
            raise HTTPException(404, "页面不存在")
        if requested.is_file():
            return FileResponse(requested)
        if asset.startswith("assets/") or Path(asset).suffix:
            raise HTTPException(404, "文件不存在")
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(503, "前端尚未构建，请运行启动脚本")
        return FileResponse(index)

    return app


app = create_app()
