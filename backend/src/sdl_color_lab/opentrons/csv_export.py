"""Export exactly one six-round session candidate for the OT-2 protocol."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re

from sdl_color_lab.core.common import validate_recipe


ROBOT_CSV_FIELDS = (
    "iteration",
    "execution_index",
    "recipe_id",
    "replicate",
    "well",
    "water_ul",
    "red_ul",
    "green_ul",
    "blue_ul",
)


def recipe_csv_filename(decision: dict, model_id: str) -> str:
    """Name the download from the same decision used to produce its contents."""
    model = "BO-EI" if decision["method"] == "bo" else model_id
    model = re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("._-")[:100] or "GPT"
    return f"{model}_R{decision['round']:02d}_{decision['dest_well']}.csv"


def export_recipe_csv(decision: dict, execution_index: int) -> str:
    """Return a deterministic CSV; repeated downloads never allocate new tips.

    ``decision`` is the workflow's pending/recorded decision, including method,
    round, dest_well and recipe. The session fixes llm=A1..A6, bo=B1..B6.
    """
    if not isinstance(decision, dict):
        raise ValueError("Decision must be an object")
    method, iteration = decision.get("method"), decision.get("round")
    if method not in ("llm", "bo"):
        raise ValueError("Robot session method must be llm or bo")
    if type(iteration) is not int or iteration not in range(1, 7):
        raise ValueError("Robot iteration must be an integer from 1 to 6")
    expected_execution = iteration + (6 if method == "bo" else 0)
    if type(execution_index) is not int or execution_index != expected_execution:
        raise ValueError("execution_index must match the method and round")
    well = decision.get("dest_well")
    expected_well = f"{'A' if method == 'llm' else 'B'}{iteration}"
    if (
        not isinstance(well, str)
        or re.fullmatch(r"[A-H](?:[1-9]|1[0-2])", well) is None
    ):
        raise ValueError("dest_well must be a 96-well position")
    if well != expected_well:
        raise ValueError(f"This session requires destination {expected_well}")
    recipe = validate_recipe(decision.get("recipe"))
    if decision.get("repeat", 1) != 1:
        raise ValueError("The six-round robot session has one repeat")
    identity = {
        key: decision.get(key)
        for key in (
            "run_id",
            "target_id",
            "method",
            "repeat",
            "round",
            "dest_well",
            "recipe",
        )
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(ROBOT_CSV_FIELDS)
    writer.writerow(
        [
            iteration,
            execution_index,
            f"{method}-{iteration}-{digest}",
            1,
            well,
            recipe["water"],
            recipe["Red"],
            recipe["Green"],
            recipe["Blue"],
        ]
    )
    return stream.getvalue()
