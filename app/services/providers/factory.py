"""
ProviderFactory — selects and caches the active FlightDataProvider.

Set FLIGHT_DATA_PROVIDER=airlabs (default) or FLIGHT_DATA_PROVIDER=simulated.
The provider is instantiated once at startup and reused for all poll cycles.
"""
import os
from .base import FlightDataProvider

_instance: FlightDataProvider | None = None


def get_provider() -> FlightDataProvider:
    global _instance
    if _instance is None:
        _instance = _build()
    return _instance


def _build() -> FlightDataProvider:
    name = os.getenv("FLIGHT_DATA_PROVIDER", "simulated").lower()
    if name == "simulated":
        from .simulated import SimulatedProvider
        return SimulatedProvider()
    from .airlabs import AirLabsProvider
    return AirLabsProvider()
