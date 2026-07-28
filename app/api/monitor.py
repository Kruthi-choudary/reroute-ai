from fastapi import APIRouter
from app.services.flight_monitor import get_state, POLL_INTERVAL_SEC
from app.services.providers import get_provider

router = APIRouter()


@router.get("/status")
def monitor_status():
    state    = get_state()
    provider = get_provider()
    return {
        "provider":              provider.name,
        "last_poll_at":          state.last_poll_at,
        "active_trips_monitored": state.trips_last_poll,
        "api_calls_last_cycle":  state.api_calls_this_cycle,
        "disruptions_detected":  state.disruptions_detected,
        "poll_interval_sec":     POLL_INTERVAL_SEC,
    }


@router.post("/reset-scenario")
def reset_scenario():
    """Reset simulated provider state — useful to replay a demo without restarting."""
    provider = get_provider()
    if hasattr(provider, "reset"):
        provider.reset()
        return {"message": "Scenario state reset"}
    return {"message": "Active provider has no reset (not simulated)"}
