"""Pydantic models matching the Boatrace Open API JSON schema."""

from __future__ import annotations

from pydantic import BaseModel, field_validator


# ── Programs API ──────────────────────────────────────────────


class BoatEntry(BaseModel):
    """A single boat/racer entry in a race program."""

    racer_boat_number: int
    racer_name: str
    racer_number: int
    racer_class_number: int
    racer_branch_number: int
    racer_birthplace_number: int
    racer_age: int
    racer_weight: float
    racer_flying_count: int
    racer_late_count: int
    racer_average_start_timing: float | None = None
    racer_national_top_1_percent: float
    racer_national_top_2_percent: float
    racer_national_top_3_percent: float
    racer_local_top_1_percent: float
    racer_local_top_2_percent: float
    racer_local_top_3_percent: float
    racer_assigned_motor_number: int
    racer_assigned_motor_top_2_percent: float
    racer_assigned_motor_top_3_percent: float
    racer_assigned_boat_number: int
    racer_assigned_boat_top_2_percent: float
    racer_assigned_boat_top_3_percent: float


class RaceProgram(BaseModel):
    """A single race entry from the programs API."""

    race_date: str
    race_stadium_number: int
    race_number: int
    race_closed_at: str
    race_grade_number: int
    race_title: str
    race_subtitle: str
    race_distance: int
    boats: list[BoatEntry]


class ProgramsResponse(BaseModel):
    """Top-level response from the programs API."""

    programs: list[RaceProgram]


# ── Results API ───────────────────────────────────────────────


class Payout(BaseModel):
    """A single payout entry."""

    combination: str
    payout: int


class Payouts(BaseModel):
    """All payout types for a race."""

    trifecta: list[Payout]
    trio: list[Payout]
    exacta: list[Payout]
    quinella: list[Payout]
    quinella_place: list[Payout]
    win: list[Payout]
    place: list[Payout]


class BoatResult(BaseModel):
    """A single boat's result."""

    racer_boat_number: int
    racer_course_number: int | None = None
    racer_start_timing: float | None = None
    racer_place_number: int | None = None
    racer_number: int | None = None
    racer_name: str | None = None


class RaceResult(BaseModel):
    """A single race result."""

    race_date: str
    race_stadium_number: int
    race_number: int
    race_wind: int | None = None
    race_wind_direction_number: int | None = None
    race_wave: int | None = None
    race_weather_number: int | None = None
    race_temperature: float | None = None
    race_water_temperature: float | None = None
    race_technique_number: int | None = None
    boats: list[BoatResult]
    payouts: Payouts


class ResultsResponse(BaseModel):
    """Top-level response from the results API."""

    results: list[RaceResult]


# ── Prediction Models ─────────────────────────────────────────


class PredictionResult(BaseModel):
    """Structured prediction from Claude API."""

    predicted_order: list[int]
    confidence: float
    recommended_bets: list[str]
    analysis: str

    @field_validator("predicted_order")
    @classmethod
    def validate_predicted_order(cls, v: list[int]) -> list[int]:
        if len(v) != 6:
            raise ValueError(f"predicted_order must have 6 elements, got {len(v)}")
        if set(v) != {1, 2, 3, 4, 5, 6}:
            raise ValueError(f"predicted_order must contain exactly boats 1-6, got {v}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {v}")
        return v
