import os
import httpx
from datetime import datetime
from typing import Optional

from .base import FlightDataProvider, FlightStatusResult

_BASE = "https://airlabs.co/api/v9"


class AirLabsProvider(FlightDataProvider):

    def __init__(self) -> None:
        self._api_key = os.getenv("AIRLABS_API_KEY", "")

    def get_flight_status(
        self,
        flight_iata: str,
        dep_iata:    str,
        arr_iata:    str,
    ) -> Optional[FlightStatusResult]:
        if not self._api_key:
            return None
        try:
            resp = httpx.get(
                f"{_BASE}/schedules",
                params={
                    "api_key":     self._api_key,
                    "flight_iata": flight_iata,
                    "dep_iata":    dep_iata,
                    "arr_iata":    arr_iata,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            flights = resp.json().get("response", [])
            if not flights:
                return None
            return self._parse(flights[0])
        except Exception as exc:
            import logging
            logging.getLogger("providers.airlabs").warning(
                "AirLabs request failed", extra={"flight": flight_iata, "error": str(exc)}
            )
            return None

    def _parse(self, f: dict) -> FlightStatusResult:
        return FlightStatusResult(
            flight_iata     = f.get("flight_iata", ""),
            status          = f.get("status", "scheduled"),
            dep_delayed_min = int(f.get("dep_delayed") or 0),
            arr_delayed_min = int(f.get("arr_delayed") or f.get("delayed") or 0),
            dep_estimated   = self._dt(f.get("dep_estimated_utc") or f.get("dep_estimated")),
            arr_estimated   = self._dt(f.get("arr_estimated_utc") or f.get("arr_estimated")),
            raw             = f,
        )

    @staticmethod
    def _dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace(" ", "T"))
        except ValueError:
            return None
