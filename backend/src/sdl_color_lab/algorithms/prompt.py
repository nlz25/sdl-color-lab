"""
psi_benchmark/tasks/color_matching/prompt.py

Construct English task and feedback messages for each LLM participant.

Migrated from: skills/automated-experiment/scripts/benchmark_schema.py
"""

from __future__ import annotations

import textwrap


def _reagent_label(name: str) -> str:
    return "purified water" if name == "water" else name + " dye solution"


def build_participant_prompt(
    target_lab: list[float],
    base_colors_lab: dict[str, list[float]],
    max_budget: int = 12,
    single_recipe: bool = True,
    target_rgb: list[int] | None = None,
    base_colors: dict[str, list[int]] | None = None,
    cold_start: bool = False,
) -> str:
    """Build the complete English user message for one benchmark round.

    Parameters
    ----------
    target_lab       : target Lab values [L, a, b]
    base_colors_lab  : base colour Lab values
    max_budget       : total experiment budget (shown in evaluation criteria)
    single_recipe    : if True, prompt enforces exactly 1 recipe per round
    target_rgb       : target colour RGB, e.g. [143, 150, 106]; shown as reference when provided
    base_colors      : measured base-colour RGB values; shown as reference when provided
    """
    r, g, b = target_rgb if target_rgb is not None else (None, None, None)

    # ── base colour section ──────────────────────────────────────────────
    base_lines = []
    for i, (name, lab) in enumerate(base_colors_lab.items()):
        line = f"{i + 1}. {name} measured base-colour Lab: (L={lab[0]:.2f}, a={lab[1]:.2f}, b={lab[2]:.2f})"
        if base_colors and name in base_colors:
            rgb = base_colors[name]
            line += f" (reference RGB: {rgb[0]}, {rgb[1]}, {rgb[2]})"
        base_lines.append(line)
    base_section = "\n".join(base_lines)

    # ── reagent names derived from base_colors_lab keys ──────────────────
    # Measured water may already be present; deduplicate while preserving order.
    reagent_names = (
        ["Red", "Green", "Blue", "water"]
        if cold_start
        else list(dict.fromkeys([*base_colors_lab.keys(), "water"]))
    )
    reagent_list = "\n".join(
        f"{i + 1}. {name} ({_reagent_label(name)})"
        for i, name in enumerate(reagent_names)
    )

    recipe_fmt_fields = ", ".join(f'"{k}": int' for k in reagent_names)
    recipe_sum = " + ".join(f'"{k}"' for k in reagent_names)

    L, a_val, b_val = target_lab
    rgb_ref = f" (reference RGB: {r}, {g}, {b})" if r is not None else ""
    target_desc = f"Lab = (L={L:.2f}, a={a_val:.2f}, b={b_val:.2f}){rgb_ref}"
    target_ref = f"Lab = (L={L:.2f}, a={a_val:.2f}, b={b_val:.2f})"

    # ── task section ─────────────────────────────────────────────────────
    if single_recipe:
        task_section = textwrap.dedent("""\
            🎯 Your task
            1. Submit exactly 1 candidate recipe this round. Your strategy should minimise Delta E 2000.
            2. Propose a reasonable experimental recipe and explain your choice in English.""")
    else:
        task_section = textwrap.dedent("""\
            🎯 Your task
            Decide how many candidate recipes to submit this round and output them.
            Requirements:
            1. You may submit one or more candidates. Multiple recipes should serve distinct exploration goals rather than be nearly identical. Your strategy should minimise Delta E 2000.
            2. Explain why you chose this number of candidates.
            3. Propose reasonable experimental recipes and explain your choices in English.""")

    # ── output format section ─────────────────────────────────────────────
    if single_recipe:
        output_section = textwrap.dedent(f"""\
            📤 Output format
            Output strictly the following JSON structure. Do not add fields or any text outside the JSON:
            {{"reasoning": "Reason for choosing this candidate recipe, in English", "recipe": {{{recipe_fmt_fields}}}}}""")
    else:
        output_section = textwrap.dedent(f"""\
            📤 Output format
            Output strictly the following JSON structure. Do not add fields or any text outside the JSON:
            {{"reasoning": "Reason for submitting these recipes this round, in English", "recipes": [{{{recipe_fmt_fields}}}]}}""")

    if cold_start:
        if base_colors_lab or base_colors:
            raise ValueError("Cold-start prompts cannot include measured base colours")
        initial_information = (
            "📊 Initial information\n"
            "Only the reagent names Red, Green, Blue dye solutions and water are provided; no measured base-dye RGB, Lab or spectra are available.\n"
            "There are no experimental observations in round 1. Propose an exploratory recipe directly; in later rounds, iterate using only this method's completed experimental feedback.\n"
            "You may use general knowledge associated with the colour names, but do not treat assumed base-colour values as measurements."
        )
    else:
        initial_information = (
            f"📊 Known base-colour measurements\n{base_section}\n"
            "These base-colour values were measured with the experimental equipment. Base your reasoning on these measurements."
        )

    # ── assemble prompt from named sections ───────────────────────────────
    parts: list[str] = [
        "You are an expert in physical science experiments participating in an automated colour-matching evaluation.",
        f"🎨 Experimental objective\n"
        f"Propose this round's candidate recipe for the target colour {target_desc}, to be tested on the experimental platform.",
        f"🧪 Available reagents\n"
        f"{reagent_list}\n\n"
        f"{initial_information}",
    ]

    parts += [
        f"📐 Recipe constraints\n"
        f"1. Each candidate must have a total volume of 200 microlitres: {recipe_sum} = 200 μL.\n"
        f"2. All volumes in each candidate must be non-negative integers, using this structure: {{{recipe_fmt_fields}}}.",
    ]

    if not single_recipe:
        parts.append(
            "Therefore:\n"
            "1. You may submit one or more candidate recipes this round.\n"
            "2. More recipes allow broader exploration but consume more of the remaining testing budget. Use the budget carefully.\n"
            "3. Balance exploration this round, the budget for later iterations and convergence efficiency."
        )

    parts += [
        f"📏 Evaluation criteria\n"
        f"1. The primary metric is Delta E 2000 (CIEDE2000), a colour-difference formula that quantifies perceptual differences between colours. Minimise Delta E 2000 and converge as quickly as possible within a maximum of {max_budget} tests.\n"
        f"2. The system measures each candidate's actual colour and calculates Delta E 2000 against the target {target_ref}.\n"
        f"3. Success means Delta E 2000 <= 1, including exactly 1. Complete all {max_budget} tests even if success is reached early.\n"
        f"4. Quality guide: Delta E 2000 < 1 is excellent, with almost no visible difference; < 2 is very good, with a very small difference; 2–3 is good, with a subtly perceptible difference; 3–5 is acceptable, with a clearly perceptible difference; > 5 indicates a substantial difference and poor colour accuracy.",
        task_section,
        output_section,
    ]

    return "\n\n".join(parts)


def build_feedback_prompt(
    obs,
    target: dict,
    budget_remaining: int,
    max_budget: int,
) -> str:
    """Build the English feedback user message after each experimental round.

    Include measurements, the target, remaining budget and the output format
    so that essential information remains available throughout the conversation.
    """
    measurements = obs.result.get("measurements", [])
    recipes = obs.action.data.get("recipes", [])

    result_lines = [f"📊 Experimental results for round {obs.iteration}"]
    for i, meas in enumerate(measurements):
        recipe = recipes[i] if i < len(recipes) else {}
        recipe_str = ", ".join(f"{k}:{v}μL" for k, v in recipe.items() if v > 0)
        lab = meas.get("measured_lab", [])
        de = meas.get("delta_e_2000")
        lab_str = (
            f"(L={lab[0]:.2f}, a={lab[1]:.2f}, b={lab[2]:.2f})"
            if len(lab) >= 3
            else "—"
        )
        de_str = f"{de:.2f}" if de is not None else "—"
        result_lines += [
            f"Recipe: {recipe_str}",
            f"Measured Lab: {lab_str}; Delta E 2000: {de_str}",
        ]

    target_lab = target.get("lab") or []
    target_rgb = target.get("rgb") or []
    L, a, b = (target_lab + [0, 0, 0])[:3]
    rgb_ref = (
        f" (reference RGB: {target_rgb[0]}, {target_rgb[1]}, {target_rgb[2]})"
        if len(target_rgb) >= 3
        else ""
    )
    used = max_budget - budget_remaining
    reagent_names = (
        list(dict.fromkeys(recipes[0].keys()))
        if recipes
        else ["Red", "Green", "Blue", "water"]
    )
    recipe_fmt_fields = ", ".join(f'"{k}": int' for k in reagent_names)

    recipe_sum = " + ".join(f'"{k}"' for k in reagent_names)

    parts = [
        "\n".join(result_lines),
        f"🎨 Target colour\nLab = (L={L:.2f}, a={a:.2f}, b={b:.2f}){rgb_ref}",
        f"💰 Experimental budget\nThis evaluation allows at most {max_budget} tests: {used} used, {budget_remaining} remaining. Submit exactly 1 candidate per round. Success means Delta E 2000 <= 1; complete all {max_budget} tests even if success is reached early.",
        f"📐 Recipe constraints\n1. Each candidate must have a total volume of 200 microlitres: {recipe_sum} = 200 μL.\n2. All volumes in each candidate must be non-negative integers, using this structure: {{{recipe_fmt_fields}}}.",
        "🎯 Your task\n1. Submit exactly 1 candidate recipe this round. Your strategy should minimise Delta E 2000.\n2. Propose a reasonable experimental recipe and explain your choice in English.",
        f'📤 Output format\nOutput strictly the following JSON structure. Do not add fields or any text outside the JSON:\n{{"reasoning": "Reason for choosing this candidate recipe, in English", "recipe": {{{recipe_fmt_fields}}}}}',
    ]
    return "\n\n".join(parts)
