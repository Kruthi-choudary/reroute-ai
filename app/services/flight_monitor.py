"""
Flight Monitor — polls active trips for disruptions.

Deliberately provider-agnostic: calls FlightDataProvider.get_flight_status()
and never imports AirLabsProvider or SimulatedProvider directly.
"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.database import SessionLocal
from app.models import (
    Trip, FlightSegment, DisruptionEvent,
    TripStatus, FlightStatus, DisruptionType, DisruptionSeverity,
)
from app.services.providers import get_provider, FlightStatusResult

DELAY_THRESHOLD   = 30    # minutes — detect disruption above this
LOOKAHEAD_HOURS   = 6     # only check segments departing within this window
POLL_INTERVAL_SEC = 300   # overridden by env var in main.py

logger = logging.getLogger("monitor")


@dataclass
class MonitorState:
    last_poll_at:         Optional[datetime] = None
    trips_last_poll:      int  = 0
    api_calls_this_cycle: int  = 0
    disruptions_detected: int  = 0
    provider_name:        str  = ""


_state = MonitorState()


def get_state() -> MonitorState:
    return _state


def check_active_trips() -> None:
    import os
    global _state

    provider = get_provider()
    db       = SessionLocal()
    calls    = 0
    found    = 0

    try:
        active = db.query(Trip).filter(
            Trip.status.in_([TripStatus.HEALTHY, TripStatus.AT_RISK])
        ).all()

        _state.last_poll_at     = datetime.now(timezone.utc)
        _state.trips_last_poll  = len(active)
        _state.provider_name    = provider.name

        if not active:
            logger.info("poll_cycle", extra={"trips": 0, "provider": provider.name})
            return

        for trip in active:
            disrupted = _check_trip(db, trip, provider)
            calls    += len(_get_upcoming(trip))
            found    += disrupted

        _state.api_calls_this_cycle = calls
        _state.disruptions_detected += found

        logger.info("poll_cycle", extra={
            "trips":        len(active),
            "segments":     calls,
            "disruptions":  found,
            "provider":     provider.name,
        })
    finally:
        db.close()


def _get_upcoming(trip: Trip) -> list:
    now       = datetime.now(timezone.utc).replace(tzinfo=None)
    lookahead = now + timedelta(hours=LOOKAHEAD_HOURS)
    return [
        seg for seg in trip.flight_segments
        if seg.status not in (FlightStatus.COMPLETED, FlightStatus.CANCELLED)
        and seg.scheduled_departure is not None
        and now <= seg.scheduled_departure <= lookahead
    ]


def _check_trip(db, trip: Trip, provider) -> int:
    found = 0
    for seg in _get_upcoming(trip):
        result = provider.get_flight_status(
            seg.flight_number,
            seg.origin_airport,
            seg.destination_airport,
        )
        if result is None:
            continue

        disruption = _classify(seg, result)
        if not disruption:
            continue

        if _already_recorded(db, trip.id, seg.id, disruption):
            continue

        logger.warning("disruption_detected", extra={
            "trip":    trip.name,
            "flight":  seg.flight_number,
            "type":    disruption["type"].value,
            "delay":   disruption.get("delay_min", 0),
            "source":  provider.name,
        })
        _trigger_recovery(db, trip, seg, disruption)
        found += 1
    return found


def _classify(seg: FlightSegment, r: FlightStatusResult) -> Optional[dict]:
    if r.status == "cancelled":
        return {
            "type":        DisruptionType.CANCELLATION,
            "severity":    DisruptionSeverity.CRITICAL,
            "description": f"{seg.flight_number} cancelled",
            "new_estimated_arrival": None,
            "delay_min":   0,
        }

    delay = r.arr_delayed_min
    if not delay and r.arr_estimated and seg.scheduled_arrival:
        try:
            delay = max(0, int((r.arr_estimated - seg.scheduled_arrival).total_seconds() / 60))
        except Exception:
            delay = 0

    if delay >= DELAY_THRESHOLD:
        new_arrival = r.arr_estimated or (
            seg.scheduled_arrival + timedelta(minutes=delay)
            if seg.scheduled_arrival else None
        )
        severity = (DisruptionSeverity.CRITICAL if delay >= 120 else
                    DisruptionSeverity.HIGH      if delay >= 60  else
                    DisruptionSeverity.MEDIUM)
        return {
            "type":        DisruptionType.DELAY,
            "severity":    severity,
            "description": f"{seg.flight_number} delayed {delay} min",
            "new_estimated_arrival": new_arrival,
            "delay_min":   delay,
        }

    return None


def _already_recorded(db, trip_id: int, seg_id: int, disruption: dict) -> bool:
    import hashlib
    key = hashlib.sha256(
        f"{trip_id}:{seg_id}:{disruption['type']}:{disruption.get('new_estimated_arrival')}".encode()
    ).hexdigest()
    return db.query(DisruptionEvent).filter(DisruptionEvent.idempotency_key == key).first() is not None


def _trigger_recovery(db, trip: Trip, seg: FlightSegment, disruption: dict) -> None:
    from app.api.disruptions import DisruptionIn, report_disruption
    from app.core.recovery_orchestrator import start_recovery

    data   = DisruptionIn(
        trip_id=trip.id,
        flight_segment_id=seg.id,
        disruption_type=disruption["type"],
        severity=disruption["severity"],
        new_estimated_arrival=disruption.get("new_estimated_arrival"),
        description=disruption["description"],
    )
    result = report_disruption(data, db)

    threading.Thread(
        target=start_recovery,
        args=(trip.id, result["id"]),
        daemon=True,
    ).start()
