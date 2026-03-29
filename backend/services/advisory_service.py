import os
from pydantic import BaseModel

from google import genai
from google.genai import types

from models.schemas import PreflightPerformanceResponse


class AdvisoryServiceError(Exception):
    """Raised when advisory generation fails."""


class AdvisoryStructuredOutput(BaseModel):
    selected_route_id: str
    reasoning: str
    advisory_text: str


class GeminiAdvisoryService:
    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        if not self.api_key:
            raise AdvisoryServiceError(
                "Missing GEMINI_API_KEY. Put it in backend/.env and restart the server."
            )

        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def _build_route_payload(perf: PreflightPerformanceResponse) -> dict:
        routes = []

        for route in perf.routes_performance:
            routes.append(
                {
                    "route_id": route.route.route_id,
                    "route_type": route.route.type,
                    "total_distance_nm": route.total_distance_nm,
                    "total_time_min": route.total_time_min,
                    "total_fuel_kg": route.total_fuel_kg,
                    "total_co2_kg": route.total_co2_kg,
                }
            )

        return {
            "flight_request": {
                "origin": perf.request.origin,
                "destination": perf.request.destination,
                "aircraft": perf.request.aircraft,
                "objective": perf.objective_used,
                "tas_used_kt": perf.tas_used_kt,
                "aircraft_mass_kg": perf.aircraft_mass_kg,
                "cruise_altitude_ft": perf.cruise_altitude_ft,
            },
            "routes": routes,
        }

    def _build_prompt(self, perf: PreflightPerformanceResponse) -> str:
        payload = self._build_route_payload(perf)

        return f"""
You are an aviation route advisory assistant.

You will receive structured route comparison data.
Your task is to decide the single best overall route.

Rules:
- Use only the provided numbers.
- Do not invent any facts.
- Consider fuel, time, and CO2 together.
- Prefer routes that are operationally efficient overall.
- If tradeoffs exist, explain them briefly.
- Keep reasoning concise.
- Start advisory_text with: "Recommended route:"
- Include the chosen route_id explicitly.

Data:
{payload}
""".strip()

    def generate_advisory(self, perf: PreflightPerformanceResponse) -> dict:
        prompt = self._build_prompt(perf)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AdvisoryStructuredOutput,
                ),
            )
        except Exception as e:
            raise AdvisoryServiceError(f"Gemini request failed: {e}") from e

        parsed = getattr(response, "parsed", None)
        if parsed is None:
            raise AdvisoryServiceError("Gemini returned no parsed structured output.")

        if isinstance(parsed, AdvisoryStructuredOutput):
            return parsed.model_dump()

        if isinstance(parsed, dict):
            return parsed

        raise AdvisoryServiceError(f"Unexpected structured output type: {type(parsed)}")