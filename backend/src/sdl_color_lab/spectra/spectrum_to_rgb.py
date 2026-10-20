"""Absorbance → sRGB and Lab, using colour-science >= 0.4.0.

Extracted from PSI-Bench's labs/psi_lab_v1/utils/spectrum_to_rgb.py without
plotting/device code. colour.sd_to_XYZ applies the correct scalar Y white-point
normalisation; XYZ must not be divided componentwise by the white point.
Input absorbance must already be solvent/container blank-corrected, at the same
optical path as the target. CSV columns: wavelength_nm,absorbance.
"""

from __future__ import annotations

import csv
import io

import colour
import numpy as np


def absorbance_to_color(wavelengths, absorbance) -> dict:
    """Convert a 380–780 nm spectrum under D65 / CIE 1931 2°.

    Wavelengths must be increasing, unique, and at most 10 nm apart.
    RGB is clipped/rounded for display; Lab preserves the measured colour.
    """
    wavelengths = np.asarray(wavelengths, dtype=float)
    absorbance = np.asarray(absorbance, dtype=float)
    if (
        wavelengths.ndim != 1
        or absorbance.ndim != 1
        or len(wavelengths) != len(absorbance)
        or len(wavelengths) < 2
        or not np.all(np.isfinite(wavelengths))
        or not np.all(np.isfinite(absorbance))
    ):
        raise ValueError("Provide equal-length, finite one-dimensional arrays")
    gaps = np.diff(wavelengths)
    if np.any(gaps <= 0) or np.any(gaps > 10):
        raise ValueError(
            "Wavelengths must be increasing and unique, with gaps <= 10 nm"
        )
    if wavelengths[0] > 380 or wavelengths[-1] < 780:
        raise ValueError("Spectrum must cover the complete 380–780 nm range")
    if np.any(absorbance < 0):
        raise ValueError(
            "Negative absorbance: check solvent/container blank correction first"
        )

    grid = np.arange(380, 781)
    transmission = 10.0 ** -np.interp(grid, wavelengths, absorbance)
    shape = colour.SpectralShape(380, 780, 1)
    observer = "CIE 1931 2 Degree Standard Observer"
    cmfs = colour.MSDS_CMFS[observer].copy().align(shape)
    illuminant = colour.SDS_ILLUMINANTS["D65"].copy().align(shape)
    whitepoint = colour.CCS_ILLUMINANTS[observer]["D65"]
    spectrum = colour.SpectralDistribution(transmission, grid)
    with colour.utilities.domain_range_scale("reference"):
        xyz = colour.sd_to_XYZ(spectrum, cmfs, illuminant, method="Integration") / 100
        lab = colour.XYZ_to_Lab(xyz, illuminant=whitepoint)
        rgb = colour.XYZ_to_sRGB(xyz, illuminant=whitepoint)
    return {
        "rgb": np.rint(np.clip(rgb, 0, 1) * 255).astype(int).tolist(),
        "lab": lab.tolist(),
        "out_of_gamut": bool(np.any(rgb < -1e-4) or np.any(rgb > 1 + 1e-4)),
    }


def spectrum_csv_to_color(text: str) -> dict:
    """Convert a single immutable snapshot of blank-corrected CSV text."""
    with io.StringIO(text, newline="") as stream:
        reader = csv.DictReader(stream)
        columns = {
            ("wavelength_nm", "absorbance"): ("wavelength_nm", "absorbance"),
            ("Wavelength(nm)", "OD Value"): ("Wavelength(nm)", "OD Value"),
        }.get(tuple(reader.fieldnames or []))
        if columns is None:
            raise ValueError(
                "CSV requires wavelength_nm,absorbance or Wavelength(nm),OD Value"
            )
        rows = list(reader)
    return absorbance_to_color(
        [float(row[columns[0]]) for row in rows],
        [float(row[columns[1]]) for row in rows],
    )
