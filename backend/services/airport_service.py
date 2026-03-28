from pathlib import Path
from typing import Dict, Optional, Union

import pandas as pd

from backend.models.schemas import AirportResponse


class AirportLookupError(Exception):
    """Raised when an airport cannot be found or the dataset is invalid."""


class AirportLookupService:
    """
    Dynamic airport lookup service backed by airports.csv.

    Expected columns from the uploaded dataset include:
    - ident
    - type
    - name
    - latitude_deg
    - longitude_deg
    - iso_country
    - municipality
    - icao_code
    - iata_code
    - gps_code
    - local_code
    """

    DEFAULT_ALLOWED_TYPES = {
        "large_airport",
        "medium_airport",
        "small_airport",
    }

    LOOKUP_COLUMNS = [
        "iata_code",
        "icao_code",
        "gps_code",
        "local_code",
        "ident",
    ]

    def __init__(
        self,
        airport_file: Union[str, Path],
        allowed_types: Optional[set[str]] = None,
    ) -> None:
        self.airport_file = Path(airport_file)
        if not self.airport_file.exists():
            raise FileNotFoundError(f"Airport file not found: {self.airport_file}")

        self.allowed_types = allowed_types or self.DEFAULT_ALLOWED_TYPES
        self.df: Optional[pd.DataFrame] = None
        self.lookup_maps: Dict[str, Dict[str, dict]] = {}

        self._load_airports()

    def _load_airports(self) -> None:
        try:
            df = pd.read_csv(self.airport_file)
        except Exception as e:
            raise AirportLookupError(f"Failed to read airport CSV: {e}") from e

        required_columns = {
            "ident",
            "type",
            "name",
            "latitude_deg",
            "longitude_deg",
            "icao_code",
            "iata_code",
            "gps_code",
            "local_code",
        }

        missing = required_columns - set(df.columns)
        if missing:
            raise AirportLookupError(
                f"Airport CSV is missing required columns: {sorted(missing)}"
            )

        # Normalize core columns
        for col in [
            "ident",
            "icao_code",
            "iata_code",
            "gps_code",
            "local_code",
            "type",
            "name",
        ]:
            df[col] = df[col].fillna("").astype(str).str.strip()

        # Latitude / longitude cleanup
        df["latitude_deg"] = pd.to_numeric(df["latitude_deg"], errors="coerce")
        df["longitude_deg"] = pd.to_numeric(df["longitude_deg"], errors="coerce")

        # Remove rows without valid coordinates
        df = df.dropna(subset=["latitude_deg", "longitude_deg"])

        # Keep only useful airport types
        df = df[df["type"].isin(self.allowed_types)]

        # Exclude obviously closed airports if a "closed" boolean/status exists
        if "closed" in df.columns:
            # Handles bool-like, string-like, or numeric values
            df = df[
                ~df["closed"]
                .fillna(False)
                .astype(str)
                .str.lower()
                .isin({"true", "1", "yes"})
            ]

        # Build per-column lookup maps
        self.lookup_maps = {col: {} for col in self.LOOKUP_COLUMNS}

        for _, row in df.iterrows():
            record = {
                "ident": row.get("ident", ""),
                "type": row.get("type", ""),
                "name": row.get("name", ""),
                "lat": float(row["latitude_deg"]),
                "lon": float(row["longitude_deg"]),
                "icao_code": row.get("icao_code", ""),
                "iata_code": row.get("iata_code", ""),
                "gps_code": row.get("gps_code", ""),
                "local_code": row.get("local_code", ""),
                "municipality": (
                    row.get("municipality", "") if "municipality" in df.columns else ""
                ),
                "country": (
                    row.get("iso_country", "") if "iso_country" in df.columns else ""
                ),
            }

            for col in self.LOOKUP_COLUMNS:
                code = str(row.get(col, "")).strip().upper()
                if code:
                    self.lookup_maps[col][code] = record

        self.df = df

    def get_airport_record(self, code: str) -> dict:
        code = code.strip().upper()
        if not code:
            raise AirportLookupError("Airport code cannot be empty.")

        for col in self.LOOKUP_COLUMNS:
            record = self.lookup_maps[col].get(code)
            if record:
                return record

        raise AirportLookupError(f"Airport not found: {code}")

    def get_airport_response(self, code: str) -> AirportResponse:
        record = self.get_airport_record(code)
        return AirportResponse(
            code=code.strip().upper(),
            name=record["name"],
            lat=record["lat"],
            lon=record["lon"],
        )

    def exists(self, code: str) -> bool:
        code = code.strip().upper()
        if not code:
            return False

        return any(code in self.lookup_maps[col] for col in self.LOOKUP_COLUMNS)