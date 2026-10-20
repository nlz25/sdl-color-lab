"""Shared data and colour helpers; no PSI-Bench runtime dependency."""

import colour
import numpy as np

NAMES = ("Red", "Green", "Blue", "water")
DYE_NAMES = NAMES[:3]
TOTAL = 200
SUCCESS_THRESHOLD = 1.0


def rgb_to_lab(rgb: list[int]) -> list[float]:
    """Copied from psi_benchmark/utils/color.py (D65; same two-decimal rounding)."""
    arr = colour.models.eotf_sRGB(np.array(rgb, dtype=float) / 255.0)
    xyz = colour.RGB_to_XYZ(arr, colour.RGB_COLOURSPACES["sRGB"])
    lab = colour.XYZ_to_Lab(xyz)
    return [round(float(x), 2) for x in lab]


def delta_e(rgb, target_rgb) -> float:
    return float(
        colour.delta_E(rgb_to_lab(rgb), rgb_to_lab(target_rgb), method="CIE 2000")
    )


def validate_recipe(recipe: dict) -> dict:
    if not isinstance(recipe, dict) or set(recipe) != set(NAMES):
        raise ValueError("recipe must contain Red, Green, Blue and water")
    if (
        any(type(v) is not int or v < 0 for v in recipe.values())
        or sum(recipe.values()) != TOTAL
    ):
        raise ValueError("Recipe volumes must be nonnegative integers totaling 200 uL")
    return recipe


def _validate_rgb(rgb):
    if not isinstance(rgb, list) or len(rgb) != 3:
        raise ValueError("RGB must contain three numbers")
    if any(
        type(v) not in (int, float) or not 0 <= v <= 255 or not np.isfinite(v)
        for v in rgb
    ):
        raise ValueError("RGB values must be finite numbers in [0,255]")


validate_rgb = _validate_rgb


def validate_measurement_provenance(measurement):
    """Reject a contradiction with the archived colour, when supplied."""
    provenance = measurement.get("provenance")
    if provenance is None:
        return
    if not isinstance(provenance, dict):
        raise ValueError("Measurement provenance must be an object")
    source_color = provenance.get("source_color")
    if source_color is not None:
        if not isinstance(source_color, dict) or "rgb" not in source_color:
            raise ValueError("provenance.source_color must contain rgb")
        validate_rgb(source_color["rgb"])
        if source_color["rgb"] != measurement["rgb"]:
            raise ValueError("Measured RGB differs from provenance.source_color.rgb")


def validate_inputs(state, calibration, allow_exhausted=False):
    """Validate shared experiment data, optionally allowing a completed run."""
    if not isinstance(state, dict) or not isinstance(calibration, list):
        raise ValueError("Input must be an object; calibration must be a list")
    if "target_rgb" not in state:
        raise ValueError("Input requires target_rgb")
    _validate_rgb(state["target_rgb"])
    state.setdefault("history", [])
    state.setdefault("budget", 12)
    state.setdefault("seed", 0)
    if type(state["budget"]) is not int or state["budget"] < 1:
        raise ValueError("budget must be a positive integer")
    if type(state["seed"]) is not int or not 0 <= state["seed"] < 2**32:
        raise ValueError("seed must be an integer in [0,2**32)")
    if not isinstance(state["history"], list):
        raise ValueError("history must be a list")
    if len(state["history"]) > state["budget"]:
        raise ValueError("Experiment history exceeds budget")
    if len(state["history"]) == state["budget"] and not allow_exhausted:
        raise ValueError("Experiment budget exhausted")
    for section, rows in (("calibration", calibration), ("history", state["history"])):
        for index, row in enumerate(rows):
            label = f"{section}[{index}]"
            if not isinstance(row, dict):
                raise ValueError(f"{label} must be an object")
            if "recipe" not in row or "rgb" not in row:
                raise ValueError(f"{label} requires recipe and rgb")
            try:
                validate_recipe(row["recipe"])
                _validate_rgb(row["rgb"])
            except ValueError as exc:
                raise ValueError(f"{label}: {exc}") from exc
            if section == "calibration":
                name = row.get("name")
                if not isinstance(name, str) or name not in NAMES:
                    raise ValueError(f"{label} requires a valid reagent name")
                pure_recipe = {
                    reagent: TOTAL if reagent == name else 0 for reagent in NAMES
                }
                if row["recipe"] != pure_recipe:
                    raise ValueError(f"{label} must be the pure {name} 200 uL recipe")
    initialization_mode = state.get("initialization_mode", "calibrated")
    if initialization_mode not in ("cold_start", "calibrated"):
        raise ValueError("Unsupported initialization mode")
    if initialization_mode == "cold_start":
        if calibration:
            raise ValueError("Cold-start experiments cannot receive measured base colours")
        return state, calibration
    calibration_names = {row["name"] for row in calibration}
    if len(calibration) != len(calibration_names) or calibration_names not in (
        set(DYE_NAMES),
        set(NAMES),
    ):
        raise ValueError(
            "Provide one measured calibration each for Red, Green and Blue; "
            "an existing measured water calibration is optional"
        )
    return state, calibration
