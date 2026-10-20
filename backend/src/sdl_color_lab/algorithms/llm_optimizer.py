"""GPT colour-matching decisions using English task and feedback prompts."""

from __future__ import annotations

import json
import os

from sdl_color_lab.settings import load_environment
from types import SimpleNamespace

from sdl_color_lab.core.common import (
    delta_e,
    rgb_to_lab,
    validate_recipe,
)
from sdl_color_lab.algorithms.prompt import (
    build_feedback_prompt,
    build_participant_prompt,
)


def parse_response(raw: str) -> dict:
    """Check the requested JSON format and keep the original assistant response."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("A nonempty original LLM response string is required")
    response = json.loads(raw)
    if not isinstance(response, dict) or set(response) != {"reasoning", "recipe"}:
        raise ValueError("LLM JSON must contain exactly reasoning and recipe")
    if not isinstance(response["reasoning"], str):
        raise ValueError("reasoning must be a string")
    return {
        "reasoning": response["reasoning"],
        "recipe": validate_recipe(response["recipe"]),
        "response": raw,
    }


def build_messages(state: dict, calibration: list[dict]) -> list[dict[str, str]]:
    """Build English user messages and replay saved assistant responses unchanged."""
    budget = state.get("budget", 12)
    cold_start = state.get("initialization_mode") == "cold_start"
    if cold_start and calibration:
        raise ValueError("Cold-start GPT cannot receive measured base colours")
    target = {"rgb": state["target_rgb"], "lab": rgb_to_lab(state["target_rgb"])}
    base_colors = {item["name"]: item["rgb"] for item in calibration}
    initial = build_participant_prompt(
        target_lab=target["lab"],
        base_colors_lab={name: rgb_to_lab(rgb) for name, rgb in base_colors.items()},
        max_budget=budget,
        target_rgb=target["rgb"],
        base_colors=base_colors,
        cold_start=cold_start,
    )
    if not cold_start:
        initial += "\n\nInitial calibration recipes and RGB: " + json.dumps(calibration, ensure_ascii=False)
    messages = [{"role": "user", "content": initial}]
    for iteration, record in enumerate(state.get("history", []), start=1):
        if "response" not in record:
            raise ValueError(f"history[{iteration - 1}] requires the original response")
        previous = parse_response(record["response"])
        if previous["recipe"] != record["recipe"]:
            raise ValueError(f"history[{iteration - 1}] response recipe does not match")
        measurement = {
            "measured_lab": rgb_to_lab(record["rgb"]),
            "delta_e_2000": delta_e(record["rgb"], target["rgb"]),
        }
        observation = SimpleNamespace(
            iteration=iteration,
            action=SimpleNamespace(data={"recipes": [previous["recipe"]]}),
            result={"measurements": [measurement]},
        )
        feedback = build_feedback_prompt(
            observation, target, budget - iteration, budget
        )
        messages.append({"role": "assistant", "content": record["response"]})
        messages.append({"role": "user", "content": feedback})
    return messages


def _call_model(
    messages: list[dict[str, str]],
    model: str | None = None,
    *,
    base_url: str | None = None,
) -> str:
    from openai import OpenAI

    load_environment()
    model = model or os.getenv("OPENAI_MODEL", "gpt-5.4")
    if not model.startswith("gpt-"):
        raise ValueError("--model / OPENAI_MODEL must name a GPT model (gpt-...)")
    options = {"timeout": 120.0, "max_retries": 0}
    if base_url is not None:
        options["base_url"] = base_url
    try:
        with OpenAI(**options) as client:
            result = client.chat.completions.create(model=model, messages=messages)
    except Exception as exc:
        # Provider exception bodies can echo headers, URLs or supplied secrets.
        # Only retain the exception class and numeric HTTP status in archives/UI.
        status = getattr(exc, "status_code", None)
        label = f"{type(exc).__name__}"
        if isinstance(status, int):
            label += f", HTTP {status}"
        raise ValueError(
            f"GPT API request failed ({label}); no fallback was used"
        ) from None
    if not result.choices or not isinstance(result.choices[0].message.content, str):
        raise ValueError("GPT returned no text response")
    return result.choices[0].message.content
