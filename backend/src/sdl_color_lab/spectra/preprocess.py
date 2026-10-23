"""Normalize original reader files without inventing missing measurements.

Usage: python -m sdl_color_lab.spectra.preprocess INPUT --out-dir OUTPUT
Optional --sheet and --well select one scan or well. Output is idempotent;
different existing content is never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import re

from sdl_color_lab.spectra.spectrum_import import (
    discover_blocks, extract_spectrum, load_workbook_data, normalize_well, normalized_csv,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sheet")
    parser.add_argument("--well", help="Required for a two-column CSV without a well label")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    blocks = discover_blocks(load_workbook_data(raw, args.input.name))
    if args.sheet:
        blocks = [block for block in blocks if block["sheet"] == args.sheet]
    well = normalize_well(args.well) if args.well else None
    outputs, summary = {}, []
    for block in blocks:
        wells = ([well] if well and (block["orientation"] == "csv" or well in block["wells"])
                 else block.get("wells", []) if not well else [])
        if block["orientation"] == "csv" and not well:
            parser.error("A two-column CSV needs --well to bind its source.")
        for selected in wells:
            spectrum = extract_spectrum(raw, args.input.name, block, selected, require_color=False)
            sheet = re.sub(r"[^A-Za-z0-9_.-]+", "_", block["sheet"]).strip(".") or "scan"
            relative = Path(f"{sheet}_{block['block_id'][:8]}") / f"{selected}.csv"
            outputs[args.out_dir / relative] = normalized_csv(spectrum)
            summary.append({
                "file": relative.as_posix(), "source": args.input.name,
                "source_sha256": spectrum["source_sha256"], "sheet": block["sheet"],
                "well": selected, "start_nm": spectrum["original_wavelength_range_nm"][0],
                "end_nm": spectrum["original_wavelength_range_nm"][1],
                "step_nm": spectrum["sampling_interval_nm"],
                "ready_for_rgb": spectrum["ready_for_rgb"],
                "ignored_outside_band_over": len(spectrum["ignored_outside_colour_band"]),
                "conversion_error": spectrum["conversion_error"] or "",
            })
    if not summary:
        parser.error("No matching spectrum was found; check --sheet and --well.")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(summary[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(summary)
    outputs[args.out_dir / "summary.csv"] = stream.getvalue()
    # Validate every destination before writing the first output.
    for path, content in outputs.items():
        if path.exists() and path.read_bytes() != content.encode("utf-8"):
            parser.error(f"Refusing to overwrite different existing content: {path}")
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("x", encoding="utf-8", newline="") as destination:
                destination.write(content)
    print(f"Prepared {len(summary)} spectra; {sum(row['ready_for_rgb'] for row in summary)} ready for RGB. See {args.out_dir / 'summary.csv'}")


if __name__ == "__main__":
    main()
