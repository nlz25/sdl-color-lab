"""Durable, hardware-independent experiment rounds with a CSV handoff.

Only state.json commits workflow progress. A pending decision is committed before
its files are exported, so retrying a failed export never requests another recipe.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sdl_color_lab.settings import load_environment

from sdl_color_lab.core.common import (
    NAMES,
    SUCCESS_THRESHOLD,
    TOTAL,
    delta_e,
    rgb_to_lab,
    validate_inputs,
    validate_measurement_provenance,
    validate_recipe,
    validate_rgb,
)

METADATA = ("run_id", "target_id", "method", "repeat", "round", "dest_well", "recipe")
CSV_FIELDS = ("dest_well", *(f"volume_{name}_ul" for name in NAMES))
LOCK_NAME = ".workflow.lock"
SCORING = "srgb_to_lab_ciede2000"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO 8601 timestamp with a timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{field} must be an ISO 8601 timestamp with a timezone"
        ) from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return result.astimezone(timezone.utc)


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON value is not allowed: {value}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path):
    return _parse_json(path.read_text(encoding="utf-8-sig"))


def _parse_json(text: str):
    return json.loads(
        text,
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )


def _json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _canonical(value) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _snapshot_hash(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    """Replace one file atomically; temporary files always share its filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _save_state(run_dir: Path, state: dict) -> None:
    _atomic_write(run_dir / "state.json", _json_text(state))


@contextmanager
def _run_lock(run_dir: Path, *, create: bool = False):
    if create:
        run_dir.mkdir(parents=True, exist_ok=True)
    elif not run_dir.is_dir():
        raise ValueError(f"Run directory does not exist: {run_dir}")
    path = run_dir / LOCK_NAME
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            f"Run directory is locked: {path}. If no workflow process is active, "
            "explicitly remove this stale lock before retrying. "
            "Active locks are never removed automatically."
        ) from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(_json_text({"pid": os.getpid(), "created_at_utc": _utc_now()}))
            stream.flush()
            os.fsync(stream.fileno())
        yield
    finally:
        path.unlink(missing_ok=True)


def _well(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-H](?:[1-9]|1[0-2])", value):
        raise ValueError("dest_well must be a 96-well position from A1 to H12")
    return value


def _positive(value, field: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")


def _algorithm_input(state: dict) -> dict:
    config = state["config"]
    return {
        "target_rgb": config["target_rgb"],
        "budget": config["budget"],
        "seed": config["seed"],
        "history": state["history"],
        "initialization_mode": config.get("initialization_mode", "calibrated"),
    }


def _validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("config must be an object")
    for field in ("run_id", "target_id"):
        if not isinstance(config[field], str) or not config[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if config["method"] not in ("bo", "llm"):
        raise ValueError("method must be bo or llm")
    if config.get("initialization_mode", "calibrated") not in ("cold_start", "calibrated"):
        raise ValueError("Unsupported initialization mode")
    _positive(config["repeat"], "repeat")
    if config["total_volume_ul"] != TOTAL or config["scoring"] != SCORING:
        raise ValueError("This workflow requires 200 uL and sRGB-derived CIEDE2000")
    if config["method"] == "llm":
        if not isinstance(config["model"], str) or not config["model"].startswith(
            "gpt-"
        ):
            raise ValueError("LLM model must be fixed to a GPT model (gpt-...)")


def _check_metadata(actual: dict, expected: dict) -> None:
    if not isinstance(actual, dict):
        raise ValueError("Measurement must be a JSON object")
    for field in METADATA:
        if field not in actual or _canonical(actual[field]) != _canonical(
            expected[field]
        ):
            raise ValueError(f"Measurement {field} does not match the pending decision")
    validate_recipe(actual["recipe"])


def _load_state(run_dir: Path) -> dict:
    state = _read_json(run_dir / "state.json")
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("Unsupported or malformed workflow state")
    _validate_config(state["config"])
    _parse_time(state["created_at_utc"], "created_at_utc")
    calibration = state["calibration"]
    if not isinstance(calibration, dict) or not isinstance(
        calibration["source_path"], str
    ):
        raise ValueError("Missing calibration provenance")
    if not re.fullmatch(r"[a-f0-9]{64}", calibration["sha256"]):
        raise ValueError("Malformed calibration source SHA256")
    if calibration["snapshot_sha256"] != _snapshot_hash(calibration["data"]):
        raise ValueError("Calibration snapshot SHA256 mismatch")
    validate_inputs(_algorithm_input(state), calibration["data"], allow_exhausted=True)
    for round_number, record in enumerate(state["history"], start=1):
        expected = {**state["config"], "round": round_number, **record}
        expected.update({key: state["config"][key] for key in METADATA[:4]})
        expected["round"] = round_number
        _check_metadata(record, expected)
        _well(record["dest_well"])
        _parse_time(record["completed_at_utc"], "completed_at_utc")
        _check_metadata(record["measurement"], record)
    pending = state["pending"]
    if pending is not None:
        if len(state["history"]) >= state["config"]["budget"]:
            raise ValueError("Pending decision exceeds the run budget")
        expected = {**pending, **state["config"], "round": len(state["history"]) + 1}
        _check_metadata(pending, expected)
        _well(pending["dest_well"])
        _parse_time(pending["created_at_utc"], "pending.created_at_utc")
    return state


def _csv_text(fields, rows) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(rows)
    return stream.getvalue()


def _write_round_outputs(run_dir: Path, decision: dict) -> None:
    destination = run_dir / "rounds" / f"{decision['round']:03d}"
    _atomic_write(destination / "decision.json", _json_text(decision))
    row = [decision["dest_well"], *(decision["recipe"][name] for name in NAMES)]
    _atomic_write(destination / "recipe.csv", _csv_text(CSV_FIELDS, [row]))
    measurement = {field: decision[field] for field in METADATA}
    measurement.update({"rgb": None, "completed_at_utc": None})
    _atomic_write(destination / "measurement_template.json", _json_text(measurement))


def summarize(state: dict) -> dict:
    config, history = state["config"], state["history"]
    start = _parse_time(state["created_at_utc"], "created_at_utc")
    best = min(history, key=lambda row: row["delta_e_2000"]) if history else None
    first = next(
        (row for row in history if row["delta_e_2000"] <= SUCCESS_THRESHOLD), None
    )
    now = _utc_now()
    exhausted = len(history) >= config["budget"]
    endpoint = history[-1]["completed_at_utc"] if exhausted else now
    pending = state["pending"]
    return {
        **config,
        "created_at_utc": state["created_at_utc"],
        "generated_at_utc": now,
        "completed_rounds": len(history),
        "remaining_rounds": config["budget"] - len(history),
        "budget_exhausted": exhausted,
        "pending": ({key: pending[key] for key in METADATA} if pending else None),
        "best_delta_e_2000": best["delta_e_2000"] if best else None,
        "best_round": best["round"] if best else None,
        "success_threshold_delta_e_2000": SUCCESS_THRESHOLD,
        "success_threshold_inclusive": True,
        "success": first is not None,
        "first_success_round": first["round"] if first else None,
        "wall_clock_to_first_success_seconds": (
            first["elapsed_wall_seconds"] if first else None
        ),
        "wall_clock_elapsed_seconds": (
            _parse_time(endpoint, "wall_clock_endpoint_utc") - start
        ).total_seconds(),
        "wall_clock_endpoint_utc": endpoint,
        "wall_clock_definition": (
            "Run initialization to the final measurement when budget is exhausted; "
            "otherwise initialization to this report. Includes CSV handoff and waiting."
        ),
        "calibration_source_path": state["calibration"]["source_path"],
        "calibration_sha256": state["calibration"]["sha256"],
    }


def export_run(run_dir: Path, state: dict | None = None) -> dict:
    """Write derived reports. Caller must hold the run lock."""
    run_dir = Path(run_dir)
    state = state if state is not None else _load_state(run_dir)
    fields = [
        "run_id",
        "target_id",
        "method",
        "repeat",
        "round",
        "dest_well",
        *(f"volume_{name}_ul" for name in NAMES),
        "rgb_r",
        "rgb_g",
        "rgb_b",
        "lab_l",
        "lab_a",
        "lab_b",
        "delta_e_2000",
        "created_at_utc",
        "completed_at_utc",
        "recorded_at_utc",
        "elapsed_wall_seconds",
        "reasoning",
        "response",
    ]
    rows = []
    for record in state["history"]:
        rows.append(
            [
                *(record[key] for key in METADATA[:-1]),
                *(record["recipe"][name] for name in NAMES),
                *record["rgb"],
                *record["lab"],
                record["delta_e_2000"],
                record["created_at_utc"],
                record["completed_at_utc"],
                record["recorded_at_utc"],
                record["elapsed_wall_seconds"],
                record.get("reasoning", ""),
                record.get("response", ""),
            ]
        )
    summary = summarize(state)
    _atomic_write(run_dir / "history.csv", _csv_text(fields, rows))
    _atomic_write(run_dir / "summary.json", _json_text(summary))
    return summary


def init_run(args: argparse.Namespace) -> dict:
    run_dir = args.run_dir.resolve()
    calibration_path = args.calibration.resolve(strict=True)
    source = calibration_path.read_bytes()
    calibration = _parse_json(source.decode("utf-8-sig"))
    model = args.model
    if args.method == "llm":
        if model is None:
            load_environment()
            model = os.getenv("OPENAI_MODEL", "gpt-5.4")
    elif model is not None:
        raise ValueError("--model is only applicable to --method llm")
    state = {
        "schema_version": 1,
        "created_at_utc": _utc_now(),
        "config": {
            "run_id": args.run_id,
            "target_id": args.target_id,
            "method": args.method,
            "repeat": args.repeat,
            "target_rgb": args.target_rgb,
            "seed": args.seed,
            "budget": args.budget,
            "model": model,
            "total_volume_ul": TOTAL,
            "scoring": SCORING,
        },
        "calibration": {
            "source_path": str(calibration_path),
            "sha256": hashlib.sha256(source).hexdigest(),
            "snapshot_sha256": _snapshot_hash(calibration),
            "data": calibration,
        },
        "history": [],
        "pending": None,
    }
    if args.method == "llm" and getattr(args, "base_url", None):
        state["config"]["base_url"] = args.base_url
    if getattr(args, "initialization_mode", None) is not None:
        state["config"]["initialization_mode"] = args.initialization_mode
    _validate_config(state["config"])
    validate_inputs(_algorithm_input(state), calibration)
    with _run_lock(run_dir, create=True):
        if any(path.name != LOCK_NAME for path in run_dir.iterdir()):
            raise ValueError(
                f"init refuses to overwrite a nonempty run directory: {run_dir}"
            )
        _save_state(run_dir, state)
        return export_run(run_dir, state)


def _llm_decision(run_dir: Path, state: dict) -> tuple:
    from sdl_color_lab.algorithms.llm_optimizer import (
        _call_model,
        build_messages,
        parse_response,
    )

    config = state["config"]
    round_number = len(state["history"]) + 1
    messages = build_messages(_algorithm_input(state), state["calibration"]["data"])
    request = {
        **{key: config[key] for key in METADATA[:4]},
        "round": round_number,
        "model": config["model"],
        "messages": messages,
    }
    if config.get("base_url"):
        request["base_url"] = config["base_url"]
    request_path = run_dir / "llm_requests" / f"{round_number:03d}.json"
    if request_path.exists():
        if _canonical(_read_json(request_path)) != _canonical(request):
            raise ValueError("Saved LLM request conflicts with the current round")
    else:
        _atomic_write(request_path, _json_text(request))
    response_path = run_dir / "llm_responses" / f"{round_number:03d}.txt"
    raw = None
    try:
        if response_path.exists():
            raw = response_path.read_bytes().decode("utf-8")
            print(
                "Recovering the saved LLM response without a new API call.",
                file=sys.stderr,
            )
        else:
            if config.get("base_url"):
                raw = _call_model(
                    messages, config["model"], base_url=config["base_url"]
                )
            else:
                raw = _call_model(messages, config["model"])
            _atomic_write(response_path, raw)
        # The legacy parser is retained; reject ambiguous JSON keys before using it.
        _parse_json(raw)
        return parse_response(raw), messages
    except Exception as exc:
        diagnostic = {
            **{key: value for key, value in request.items() if key != "messages"},
            "failed_at_utc": _utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "response_path": str(response_path) if response_path.exists() else None,
            "raw_response": raw,
            "retry_note": (
                "No fallback decision was generated. A saved response is reused on retry; "
                "use the page's retry action to archive an invalid response. A provider timeout "
                "may have completed remotely even when no response was received."
            ),
        }
        diagnostic_path = (
            run_dir / "llm_failures" / (f"{round_number:03d}-{uuid.uuid4().hex}.json")
        )
        try:
            _atomic_write(diagnostic_path, _json_text(diagnostic))
        except OSError as diagnostic_error:
            raise ValueError(
                f"LLM round failed: {exc}; diagnostic could not be saved: {diagnostic_error}"
            ) from exc
        raise ValueError(
            f"LLM round failed: {exc}; diagnostic: {diagnostic_path}"
        ) from exc


def propose_run(run_dir: Path, dest_well: str) -> dict:
    run_dir = Path(run_dir).resolve()
    _well(dest_well)
    with _run_lock(run_dir):
        state = _load_state(run_dir)
        pending = state["pending"]
        if pending is not None:
            if dest_well != pending["dest_well"]:
                raise ValueError(
                    "A pending decision already exists for a different dest_well"
                )
            _write_round_outputs(run_dir, pending)
            print(
                "Re-exported the pending round. Re-exporting does not authorize "
                "executing the same experiment twice.",
                file=sys.stderr,
            )
            return pending
        algorithm_input = _algorithm_input(state)
        calibration = state["calibration"]["data"]
        validate_inputs(algorithm_input, calibration)
        method = state["config"]["method"]
        if method == "llm":
            result, messages = _llm_decision(run_dir, state)
        else:
            from sdl_color_lab.algorithms.bo_optimizer import suggest

            result = suggest(algorithm_input, calibration)
        validate_recipe(result["recipe"])
        pending = {
            **result,
            **{key: state["config"][key] for key in METADATA[:4]},
            "round": len(state["history"]) + 1,
            "dest_well": dest_well,
            "created_at_utc": _utc_now(),
        }
        if method == "llm":
            pending["model"] = state["config"]["model"]
            pending["prompt_sha256"] = _snapshot_hash(messages)
        state["pending"] = pending
        _save_state(run_dir, state)
        _write_round_outputs(run_dir, pending)
        return pending


def record_run(run_dir: Path, measurement_path: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    measurement = _read_json(Path(measurement_path))
    if not isinstance(measurement, dict):
        raise ValueError("Measurement must be a JSON object")
    with _run_lock(run_dir):
        state = _load_state(run_dir)
        round_number = measurement.get("round")
        _positive(round_number, "measurement.round")
        if round_number <= len(state["history"]):
            previous = state["history"][round_number - 1]
            _check_metadata(measurement, previous)
            if _canonical(previous["measurement"]) != _canonical(measurement):
                raise ValueError(
                    "Conflicting measurement for an already completed round"
                )
            result = export_run(run_dir, state)
            result["record_result"] = "already_recorded"
            return result
        pending = state["pending"]
        if pending is None:
            raise ValueError("There is no pending decision to record")
        _check_metadata(measurement, pending)
        if "rgb" not in measurement:
            raise ValueError("A real measured rgb value is required")
        validate_rgb(measurement["rgb"])
        validate_measurement_provenance(measurement)
        completed = _parse_time(measurement.get("completed_at_utc"), "completed_at_utc")
        if completed < _parse_time(pending["created_at_utc"], "pending.created_at_utc"):
            raise ValueError(
                "completed_at_utc cannot be earlier than the pending decision"
            )
        if completed > datetime.now(timezone.utc) + timedelta(seconds=5):
            raise ValueError(
                "completed_at_utc cannot be in the future (5-second clock tolerance)"
            )
        record = {
            **pending,
            "rgb": measurement["rgb"],
            "lab": rgb_to_lab(measurement["rgb"]),
            "delta_e_2000": delta_e(measurement["rgb"], state["config"]["target_rgb"]),
            "completed_at_utc": completed.isoformat().replace("+00:00", "Z"),
            "recorded_at_utc": _utc_now(),
            "elapsed_wall_seconds": (
                completed - _parse_time(state["created_at_utc"], "created_at_utc")
            ).total_seconds(),
            "measurement": measurement,
        }
        state["history"].append(record)
        state["pending"] = None
        _save_state(run_dir, state)
        result = export_run(run_dir, state)
        result["record_result"] = "recorded"
        return result
