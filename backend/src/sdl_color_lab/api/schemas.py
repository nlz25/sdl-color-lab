"""Strict HTTP payload schemas; no experiment state or filesystem access."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpectrumSelection(StrictBody):
    block: dict[str, Any]
    well: str = Field(min_length=1, max_length=4)
    expected_well: str | None = None
    target_rgb: list[StrictInt] | None = None


class CalibrationSelection(StrictBody):
    upload_id: str
    block: dict[str, Any]
    well: str


class SessionCreation(StrictBody):
    request_id: UUID
    plate_id: str | None = Field(default=None, min_length=1, max_length=100)
    target_rgb: list[StrictInt] = Field(min_length=3, max_length=3)
    blank_confirmed: StrictBool | None = None
    preflight_token: str | None = None
    calibrations: dict[str, CalibrationSelection] = Field(default_factory=dict)
    initial_method: Literal["llm", "bo"] = "llm"


class MethodSelection(StrictBody):
    method: Literal["llm", "bo"]
    preflight_token: str | None = None


class MethodAction(StrictBody):
    method: Literal["llm", "bo"] | None = None
    round_number: StrictInt | None = Field(default=None, ge=1, le=6)


class Measurement(StrictBody):
    upload_id: str
    block: dict[str, Any]
    well: str
    completed_at: str | None = None
    method: Literal["llm", "bo"]
    round_number: StrictInt = Field(ge=1, le=6)


class ImportProfile(StrictBody):
    name: str = Field(min_length=1, max_length=100)
    mapping: dict[str, Any]
