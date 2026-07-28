"""
SimulatedProvider — replays scripted scenario files.

Each call to get_flight_status() advances the state for that flight by one step.
This means:
  - Poll 1 → state[0]  (usually "no disruption")
  - Poll 2 → state[1]  (disruption appears — monitor detects, triggers recovery)
  - Poll 3+ → state[-1] (held at last state)

Select the active scenario via ACTIVE_SCENARIO env var (default: delay_165).
"""
import os
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .base import FlightDataProvider, FlightStatusResult

_SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"
logger = logging.getLogger("providers.simulated")


class SimulatedProvider(FlightDataProvider):

    def __init__(self) -> None:
        scenario_name = os.getenv("ACTIVE_SCENARIO", "delay_165")
        self._scenario = self._load(scenario_name)
        self._state_index: dict[str, int] = {}   # flight_iata → current state index
        logger.info(
            "SimulatedProvider loaded",
            extra={"scenario": scenario_name, "description": self._scenario.get("description")}
        )

    def get_flight_status(
        self,
        flight_iata: str,
        dep_iata:    str,
        arr_iata:    str,
    ) -> Optional[FlightStatusResult]:
        flights = self._scenario.get("flights", {})
        if flight_iata not in flights:
            # Not in scenario — return on-time (no disruption)
            return FlightStatusResult(flight_iata=flight_iata, status="scheduled")

        states = flights[flight_iata]["states"]
        idx    = self._state_index.get(flight_iata, 0)
        state  = states[min(idx, len(states) - 1)]

        # Advance for next call (stop at last state)
        self._state_index[flight_iata] = min(idx + 1, len(states) - 1)

        logger.debug(
            "Simulated flight status",
            extra={"flight": flight_iata, "state_index": idx, "status": state["status"],
                   "arr_delayed_min": state.get("arr_delayed_min", 0)}
        )

        return FlightStatusResult(
            flight_iata     = flight_iata,
            status          = state["status"],
            dep_delayed_min = state.get("dep_delayed_min", 0),
            arr_delayed_min = state.get("arr_delayed_min", 0),
        )

    def reset(self) -> None:
        """Reset state — useful for demo restarts without server restart."""
        self._state_index.clear()

    @staticmethod
    def _load(name: str) -> dict:
        path = _SCENARIOS_DIR / f"{name}.json"
        if not path.exists():
            logger.warning("Scenario not found, falling back to happy_path", extra={"scenario": name})
            path = _SCENARIOS_DIR / "happy_path.json"
        with path.open() as f:
            return json.load(f)
