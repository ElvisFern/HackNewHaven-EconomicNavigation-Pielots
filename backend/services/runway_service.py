from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd

from config.aircraft_defaults import AIRCRAFT_DEFAULTS


class RunwayServiceError(Exception):
    """Raised when runway data cannot be loaded or evaluated."""


class RunwayFeasibilityService:
    REQUIRED_COLUMNS = {
        "airport_ident",
        "length_ft",
        "width_ft",
        "surface",
        "lighted",
        "closed",
        "le_ident",
        "he_ident",
    }

    def __init__(self, runway_file: Union[str, Path]) -> None:
        self.runway_file = Path(runway_file)
        if not self.runway_file.exists():
            raise FileNotFoundError(f"Runway file not found: {self.runway_file}")

        self.df: Optional[pd.DataFrame] = None
        self._load_runways()

    def _load_runways(self) -> None:
        try:
            df = pd.read_csv(self.runway_file)
        except Exception as e:
            raise RunwayServiceError(f"Failed to read runway CSV: {e}") from e

        missing = self.REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise RunwayServiceError(
                f"Runway CSV is missing required columns: {sorted(missing)}"
            )

        df["airport_ident"] = df["airport_ident"].fillna("").astype(str).str.strip().str.upper()
        df["surface"] = df["surface"].fillna("").astype(str).str.strip().str.upper()
        df["le_ident"] = df["le_ident"].fillna("").astype(str).str.strip().str.upper()
        df["he_ident"] = df["he_ident"].fillna("").astype(str).str.strip().str.upper()

        df["length_ft"] = pd.to_numeric(df["length_ft"], errors="coerce")
        df["width_ft"] = pd.to_numeric(df["width_ft"], errors="coerce")
        df["lighted"] = pd.to_numeric(df["lighted"], errors="coerce").fillna(0).astype(int)
        df["closed"] = (
            df["closed"]
            .fillna(0)
            .astype(str)
            .str.strip()
            .str.lower()
            .isin({"1", "true", "yes"})
        )

        df["surface_category"] = df["surface"].apply(self._normalize_surface)

        self.df = df

    @staticmethod
    def _normalize_surface(surface: str) -> str:
        value = (surface or "").upper()

        paved_tokens = {
            "ASP", "ASPH", "ASPHALT", "CON", "CONC", "CONCRETE",
            "BIT", "BITUMINOUS", "PAVED", "PEM", "TAR", "MAC", "SEAL"
        }
        gravel_tokens = {"GRAVEL", "GVL", "GRE", "GRVL"}
        unpaved_tokens = {
            "GRASS", "GRS", "TURF", "DIRT", "EARTH", "SAND", "CLAY", "SOIL"
        }
        water_tokens = {"WATER", "WTR", "SEA", "LAKE", "RIVER"}

        if value in paved_tokens:
            return "paved"
        if value in gravel_tokens:
            return "gravel"
        if value in unpaved_tokens:
            return "unpaved"
        if value in water_tokens:
            return "water"
        if value == "":
            return "unknown"

        if any(tok in value for tok in ["ASP", "CONC", "CON", "PAVE"]):
            return "paved"
        if "GRAVEL" in value:
            return "gravel"
        if any(tok in value for tok in ["GRASS", "TURF", "DIRT", "EARTH", "SAND"]):
            return "unpaved"
        if "WATER" in value:
            return "water"

        return "unknown"

    def _get_aircraft_requirements(self, aircraft: str) -> Dict[str, Any]:
        aircraft_key = aircraft.lower()
        defaults = AIRCRAFT_DEFAULTS.get(aircraft_key)
        if not defaults:
            raise RunwayServiceError(f"Missing aircraft defaults for '{aircraft_key}'")

        mass_kg = float(defaults["mass_kg"])

        if mass_kg < 12000:
            min_length_ft = 4000
            min_width_ft = 75
        elif mass_kg < 30000:
            min_length_ft = 5000
            min_width_ft = 100
        elif mass_kg < 80000:
            min_length_ft = 6000
            min_width_ft = 100
        else:
            min_length_ft = 7000
            min_width_ft = 150

        return {
            "aircraft": aircraft_key,
            "aircraft_display_name": defaults.get("display_name", aircraft_key.upper()),
            "mass_kg": mass_kg,
            "min_runway_length_ft": min_length_ft,
            "min_runway_width_ft": min_width_ft,
            "allowed_surface_categories": ["paved"],
        }

    def evaluate_airport(self, airport_ident: str, airport_code: str, airport_name: str, aircraft: str) -> Dict[str, Any]:
        if self.df is None:
            raise RunwayServiceError("Runway data not loaded.")

        airport_ident = airport_ident.strip().upper()
        rows = self.df[self.df["airport_ident"] == airport_ident].copy()

        requirements = self._get_aircraft_requirements(aircraft)

        if rows.empty:
            return {
                "airport_ident": airport_ident,
                "airport_code": airport_code,
                "airport_name": airport_name,
                "aircraft": requirements["aircraft"],
                "aircraft_display_name": requirements["aircraft_display_name"],
                "feasible": False,
                "reason": "No runway records found for airport.",
                "required_min_runway_length_ft": requirements["min_runway_length_ft"],
                "required_min_runway_width_ft": requirements["min_runway_width_ft"],
                "allowed_surface_categories": requirements["allowed_surface_categories"],
                "total_runway_records": 0,
                "usable_runway_count": 0,
                "longest_usable_runway_ft": None,
                "matched_runway": None,
            }

        open_rows = rows[~rows["closed"]].copy()
        if open_rows.empty:
            return {
                "airport_ident": airport_ident,
                "airport_code": airport_code,
                "airport_name": airport_name,
                "aircraft": requirements["aircraft"],
                "aircraft_display_name": requirements["aircraft_display_name"],
                "feasible": False,
                "reason": "All runways at this airport are marked closed.",
                "required_min_runway_length_ft": requirements["min_runway_length_ft"],
                "required_min_runway_width_ft": requirements["min_runway_width_ft"],
                "allowed_surface_categories": requirements["allowed_surface_categories"],
                "total_runway_records": int(len(rows)),
                "usable_runway_count": 0,
                "longest_usable_runway_ft": None,
                "matched_runway": None,
            }

        usable = open_rows[
            (open_rows["length_ft"] >= requirements["min_runway_length_ft"])
            & (open_rows["width_ft"] >= requirements["min_runway_width_ft"])
            & (open_rows["surface_category"].isin(requirements["allowed_surface_categories"]))
        ].copy()

        matched_runway = None
        longest_usable = None
        if not usable.empty:
            usable = usable.sort_values(["length_ft", "width_ft"], ascending=False)
            best = usable.iloc[0]
            longest_usable = float(best["length_ft"])
            matched_runway = {
                "airport_ident": airport_ident,
                "length_ft": float(best["length_ft"]) if pd.notna(best["length_ft"]) else None,
                "width_ft": float(best["width_ft"]) if pd.notna(best["width_ft"]) else None,
                "surface": best["surface"],
                "surface_category": best["surface_category"],
                "lighted": bool(best["lighted"]),
                "le_ident": best["le_ident"],
                "he_ident": best["he_ident"],
            }

        feasible = matched_runway is not None

        if feasible:
            reason = "Airport has at least one open, suitable runway for this aircraft."
        else:
            max_length = open_rows["length_ft"].max() if not open_rows["length_ft"].isna().all() else None
            max_width = open_rows["width_ft"].max() if not open_rows["width_ft"].isna().all() else None
            surfaces = sorted(set(open_rows["surface_category"].dropna().tolist()))
            reason = (
                "No open runway satisfies the aircraft requirements. "
                f"Longest open runway: {None if pd.isna(max_length) else float(max_length)} ft; "
                f"widest open runway: {None if pd.isna(max_width) else float(max_width)} ft; "
                f"surface categories present: {surfaces}"
            )

        return {
            "airport_ident": airport_ident,
            "airport_code": airport_code,
            "airport_name": airport_name,
            "aircraft": requirements["aircraft"],
            "aircraft_display_name": requirements["aircraft_display_name"],
            "feasible": feasible,
            "reason": reason,
            "required_min_runway_length_ft": requirements["min_runway_length_ft"],
            "required_min_runway_width_ft": requirements["min_runway_width_ft"],
            "allowed_surface_categories": requirements["allowed_surface_categories"],
            "total_runway_records": int(len(rows)),
            "usable_runway_count": int(len(usable)),
            "longest_usable_runway_ft": longest_usable,
            "matched_runway": matched_runway,
        }
