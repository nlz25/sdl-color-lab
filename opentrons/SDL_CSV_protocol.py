"""SDL Hackathon: one OT-2 candidate per run, six rounds per GPT or BO experiment.

Read one candidate, add water, red, green and blue to a total of 200 uL, then mix.
CSV columns: iteration,execution_index,recipe_id,replicate,well,water_ul,red_ul,green_ul,blue_ul.
iteration is the method's round (1..6); execution_index reserves a tip block (1..12)
and does not indicate chronological execution order. Either method may run first.
GPT uses A1..A6; BO uses B1..B6. Re-downloading keeps the same tip block.
Do not rerun a CSV that has already been executed.

Deck: plate 7, source rack 8, P300 tips 10, P20 tips 11.
No modules are required; the P300 pipette performs the final mix.
Pipettes: left P20 and right P300, both single-channel.
Sources: A3 water, A4 red, B3 green, B4 blue. The inherited assumptions of 45 mL
initial volume and aspiration 40 mm above the tube bottom are unverified on site.
Both pipettes use that source-bottom position for all ingredients and pre-wetting.
Final mixing is separate and remains 2 mm above the destination well bottom.
Confirm liquid levels, tip reach and labware offsets; simulation cannot verify them.
Skip 0 uL; use P20 for 1..20 uL and P300 above 20 uL.
Use a fresh tip for each transfer and for the final mix.
EXAMPLE_CSV is a simulation-only fallback; a real run requires a supplied CSV.
Protocol API 2.28.
"""
import csv
import io
import math
from copy import deepcopy
from opentrons import protocol_api
from opentrons.protocol_api import RuntimeParameterRequiredError

metadata = {
    "protocolName": "SDL Hackthon - OT-2 CSV single well per round",
    "description": "One CSV row per run. Add water, red, green and blue to one well, then mix 100 uL once. Total 200 uL. Twelve executions use separate tip blocks; six iterations per method.",
}
requirements = {"robotType": "OT-2", "apiLevel": "2.28"}

TOTAL_UL = 200.0

MIN_NONZERO_UL = 1.0

TIP_CAPACITY_UL = 200.0

P20_MAX_UL = 20.0

P300_MAX_UL = 300.0

SOURCE_INITIAL_UL = 45000.0

SOURCE_RESERVE_UL = 1000.0

SOURCE_ASPIRATE_Z_MM = 40.0

SOURCE_ASPIRATE_POSITION = {
    "position_reference": "well-bottom",
    "offset": {"x": 0, "y": 0, "z": SOURCE_ASPIRATE_Z_MM},
}

DEST_DISPENSE_Z_MM = 2.0

MIX_VOLUME_UL = 100.0

MIX_REPETITIONS = 1

MIX_Z_MM = 2.0

MIX_ASPIRATE_RATE = 100.0

MIX_DISPENSE_RATE = 100.0

P20_ASPIRATE_RATE = 5.0

P20_DISPENSE_RATE = 5.0

P300_ASPIRATE_RATE = 100.0

P300_DISPENSE_RATE = 100.0

PLATE_SLOT = "7"

SOURCE_SLOT = "8"

P300_TIPS_SLOT = "10"

P20_TIPS_SLOT = "11"

TIP_ORDER = tuple(f"{r}{c}" for c in range(1, 13) for r in "ABCDEFGH")

PLATE_LOADNAME = "corning_96_wellplate_360ul_flat"

SOURCE_LOADNAME = "opentrons_10_tuberack_falcon_4x50ml_6x15ml_conical"

INGREDIENTS = ("water_ul", "red_ul", "green_ul", "blue_ul")

SOURCE_WELLS = {"water_ul": "A3", "red_ul": "A4", "green_ul": "B3", "blue_ul": "B4"}

EXPECTED_HEADER = ("iteration", "execution_index", "recipe_id", "replicate", "well", *INGREDIENTS)

EXAMPLE_CSV = """iteration,execution_index,recipe_id,replicate,well,water_ul,red_ul,green_ul,blue_ul
1,1,R001,1,A1,50,50,50,50
"""

TRANSFER_PROPERTIES = {'aspirate': {'aspirate_position': SOURCE_ASPIRATE_POSITION, 'flow_rate_by_volume': [[0, 100]], 'pre_wet': True, 'correction_by_volume': [[0, 0]], 'delay': {'enabled': False}, 'mix': {'enabled': False}, 'submerge': {'delay': {'enabled': False}, 'speed': 35, 'start_position': {'offset': {'x': 0, 'y': 0, 'z': 2}, 'position_reference': 'well-top'}}, 'retract': {'air_gap_by_volume': [[0, 0]], 'delay': {'enabled': False}, 'end_position': {'offset': {'x': 0, 'y': 0, 'z': 2}, 'position_reference': 'well-top'}, 'speed': 35, 'touch_tip': {'enabled': False}}}, 'dispense': {'dispense_position': {'offset': {'x': 0, 'y': 0, 'z': 2}, 'position_reference': 'well-bottom'}, 'flow_rate_by_volume': [[0, 100]], 'delay': {'enabled': False}, 'submerge': {'delay': {'enabled': False}, 'speed': 35, 'start_position': {'offset': {'x': 0, 'y': 0, 'z': 2}, 'position_reference': 'well-top'}}, 'retract': {'air_gap_by_volume': [[0, 0]], 'delay': {'enabled': False}, 'end_position': {'offset': {'x': 0, 'y': 0, 'z': 2}, 'position_reference': 'well-top'}, 'speed': 35, 'touch_tip': {'enabled': False}, 'blowout': {'enabled': False}}, 'correction_by_volume': [[0, 0]], 'push_out_by_volume': [[0, 0]], 'mix': {'enabled': False}}}
TIPS_PER_ROUND = 5



def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="input_csv", display_name="Recipe CSV",
        description="One row: iteration 1-6, execution 1-12, replicate 1, target well, integer volumes totaling 200 uL.",
    )


def validate_recipe(table):
    """Validate the round's single recipe row before any robot motion."""
    if not isinstance(table, list) or not table or not isinstance(table[0], list):
        raise ValueError("CSV must contain a header and exactly one recipe row.")
    header = [str(cell).strip() for cell in table[0]]
    if header:
        header[0] = header[0].lstrip("\ufeff")
    if len(header) != len(set(header)) or set(header) != set(EXPECTED_HEADER):
        raise ValueError("CSV header must contain exactly: " + ",".join(EXPECTED_HEADER))
    data = []
    for line, cells in enumerate(table[1:], start=2):
        if not isinstance(cells, list) or any(not isinstance(cell, str) for cell in cells):
            raise ValueError(f"CSV line {line}: expected text cells.")
        if not cells or all(not cell.strip() for cell in cells):
            continue
        if len(cells) != len(header):
            raise ValueError(f"CSV line {line}: wrong number of fields.")
        data.append((line, dict(zip(header, (cell.strip() for cell in cells)))))
    if len(data) != 1:
        raise ValueError("This protocol runs ONE well per iteration. CSV must contain exactly one recipe row.")
    line, raw = data[0]
    try:
        iteration, replicate = int(raw["iteration"]), int(raw["replicate"])
        execution_index = int(raw["execution_index"])
    except ValueError as exc:
        raise ValueError("iteration, execution_index and replicate must be integers.") from exc
    if iteration not in range(1, 7):
        raise ValueError("iteration must be an integer from 1 to 6.")
    if execution_index not in range(1, 13):
        raise ValueError("execution_index must be an integer from 1 to 12.")
    if (execution_index - 1) % 6 + 1 != iteration:
        raise ValueError("iteration must match execution_index within its six-round method.")
    if replicate != 1:
        raise ValueError("Single-well mode: keep the replicate column equal to 1.")
    if not raw["recipe_id"] or len(raw["recipe_id"]) > 64:
        raise ValueError("recipe_id must contain 1..64 characters.")
    well = raw["well"].upper()
    if well not in TIP_ORDER:
        raise ValueError(f"Invalid destination well {well!r}; use A1..H12.")
    expected_well = f"{'A' if execution_index <= 6 else 'B'}{iteration}"
    if well != expected_well:
        raise ValueError(f"execution_index {execution_index} requires well {expected_well}.")
    row = {"iteration": iteration, "execution_index": execution_index, "replicate": 1, "recipe_id": raw["recipe_id"], "well": well}
    for ingredient in INGREDIENTS:
        try:
            volume = float(raw[ingredient])
        except ValueError as exc:
            raise ValueError(f"{ingredient} must be a number in uL.") from exc
        if not math.isfinite(volume) or not 0 <= volume <= TOTAL_UL:
            raise ValueError(f"{ingredient} must be finite and within 0..200 uL.")
        if not volume.is_integer():
            raise ValueError(f"{ingredient} must be an integer volume in uL.")
        if 0 < volume < MIN_NONZERO_UL:
            raise ValueError(f"Nonzero {ingredient} must be at least 1 uL; revise/dilute the recipe.")
        if volume > SOURCE_INITIAL_UL - SOURCE_RESERVE_UL:
            raise ValueError(f"Insufficient budgeted source liquid for {ingredient}.")
        row[ingredient] = int(volume)
    if not math.isclose(sum(row[key] for key in INGREDIENTS), TOTAL_UL, rel_tol=0, abs_tol=1e-6):
        raise ValueError("The four component volumes must total 200 uL; no automatic water adjustment is performed.")
    tips = {"p20": 0, "p300": 1}  # Reserve a fresh P300 tip for the final mix.
    for key in INGREDIENTS:
        if row[key] > 0:
            tips["p20" if row[key] <= P20_MAX_UL else "p300"] += 1
    if max(tips.values()) > TIPS_PER_ROUND:
        raise ValueError("Planned transfers exceed the reserved tip block.")
    return row, tips


def starting_tip_for_execution(execution_index):
    """Reserve five tips per pipette for each of twelve IDs, without method resets."""
    if type(execution_index) is not int or execution_index not in range(1, 13):
        raise ValueError("execution_index must be an integer from 1 to 12.")
    return TIP_ORDER[(execution_index - 1) * TIPS_PER_ROUND]


def read_recipe_table(protocol):
    try:
        return protocol.params.input_csv.parse_as_csv()
    except RuntimeParameterRequiredError:
        if not protocol.is_simulating():
            raise
        protocol.comment('SIMULATION ONLY: no CSV selected; using EXAMPLE_CSV. Select the real CSV before robot use.')
        return list(csv.reader(io.StringIO(EXAMPLE_CSV), strict=True))

def make_transfer_class(protocol, pipette_name, tip_uri, aspirate_rate, dispense_rate):
    """Keep exported liquid-handling settings and apply pipette-specific flow rates."""
    properties = deepcopy(TRANSFER_PROPERTIES)
    # Override the complete position so every source aspiration, including
    # pre-wetting, is bottom-referenced for both P20 and P300.
    properties["aspirate"]["aspirate_position"] = deepcopy(SOURCE_ASPIRATE_POSITION)
    properties["dispense"]["dispense_position"]["offset"]["z"] = DEST_DISPENSE_Z_MM
    properties["aspirate"]["flow_rate_by_volume"] = [(0, aspirate_rate)]
    properties["dispense"]["flow_rate_by_volume"] = [(0, dispense_rate)]
    return protocol.define_liquid_class(
        name="sdl_" + pipette_name,
        properties={pipette_name: {tip_uri: properties}},
    )

def run(protocol: protocol_api.ProtocolContext) -> None:
    recipe, tip_counts = validate_recipe(read_recipe_table(protocol))
    if not (0 < MIX_VOLUME_UL <= min(TOTAL_UL, P300_MAX_UL)):
        raise ValueError("Mix volume exceeds sample volume or P300 capacity.")
    if not isinstance(MIX_REPETITIONS, int) or MIX_REPETITIONS < 1:
        raise ValueError("MIX_REPETITIONS must be a positive integer.")
    tips20 = protocol.load_labware(
        "opentrons_96_tiprack_20ul", P20_TIPS_SLOT,
        label="Opentrons 20 uL Tips", namespace="opentrons", version=1,
    )
    tips300 = protocol.load_labware(
        "opentrons_96_tiprack_300ul", P300_TIPS_SLOT,
        label="Opentrons 300 uL Tips", namespace="opentrons", version=1,
    )
    plate = protocol.load_labware(
        PLATE_LOADNAME, PLATE_SLOT, label="Destination", namespace="opentrons", version=5,
    )
    source = protocol.load_labware(
        SOURCE_LOADNAME, SOURCE_SLOT, label="source", namespace="opentrons", version=3,
    )
    p20 = protocol.load_instrument("p20_single_gen2", "left", tip_racks=[tips20])
    p300 = protocol.load_instrument("p300_single_gen2", "right", tip_racks=[tips300])
    start = starting_tip_for_execution(recipe["execution_index"])
    p20.starting_tip, p300.starting_tip = tips20[start], tips300[start]
    class20 = make_transfer_class(
        protocol, "p20_single_gen2", "opentrons/opentrons_96_tiprack_20ul/1",
        P20_ASPIRATE_RATE, P20_DISPENSE_RATE,
    )
    class300 = make_transfer_class(
        protocol, "p300_single_gen2", "opentrons/opentrons_96_tiprack_300ul/1",
        P300_ASPIRATE_RATE, P300_DISPENSE_RATE,
    )
    colors = {"water_ul": "#50D5FF", "red_ul": "#FF4F4F", "green_ul": "#7EFF42", "blue_ul": "#0032FF"}
    for key in INGREDIENTS:
        liquid = protocol.define_liquid(
            key.removesuffix("_ul"), description="Purified water or aqueous dye stock",
            display_color=colors[key],
        )
        source.load_liquid(wells=[SOURCE_WELLS[key]], liquid=liquid, volume=SOURCE_INITIAL_UL)
    target = plate[recipe["well"]]
    protocol.comment(f"Iteration={recipe['iteration']} execution_index={recipe['execution_index']} recipe={recipe['recipe_id']} target={recipe['well']} tips={tip_counts} start_tip={start}.")
    protocol.comment(
        f"All source aspiration and pre-wetting: bottom + {SOURCE_ASPIRATE_Z_MM:g} mm "
        "(water/red/green/blue, P20/P300). Inherited and UNVERIFIED: "
        "confirm liquid level and tip reach before robot use."
    )
    # One destination well per run; no replicates or loop over experiment rounds.
    for key in INGREDIENTS:
        volume = recipe[key]
        if volume == 0:
            continue
        pipette = p20 if volume <= P20_MAX_UL else p300
        liquid_class = class20 if volume <= P20_MAX_UL else class300
        protocol.comment(f"STAGE: {key} {volume} uL to {recipe['well']}")
        pipette.pick_up_tip()
        pipette.transfer_with_liquid_class(
            liquid_class=liquid_class, volume=volume,
            source=source[SOURCE_WELLS[key]], dest=target,
            new_tip="never", trash_location=protocol.fixed_trash,
        )
        pipette.drop_tip()
    protocol.comment(
        f"STAGE: mix {recipe['well']} at destination bottom + {MIX_Z_MM:g} mm "
        "after all components have been added"
    )
    p300.pick_up_tip()
    p300.mix(
        repetitions=MIX_REPETITIONS, volume=MIX_VOLUME_UL,
        location=target.bottom(z=MIX_Z_MM),
        aspirate_flow_rate=MIX_ASPIRATE_RATE, dispense_flow_rate=MIX_DISPENSE_RATE,
        final_push_out=0,
    )
    p300.drop_tip()
    protocol.comment("This iteration is complete. Measure externally; next run requires a new CSV and an unused well.")
