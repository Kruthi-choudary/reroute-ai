"""
Impact Analyzer — models the itinerary as a dependency graph and
propagates upstream changes to downstream segments.
"""
from datetime import datetime
from typing import List, Dict, Any

from app.models import FlightSegment, HotelBooking, Transfer, Trip

# Minimum connection buffer in minutes (configurable per airport in production)
DEFAULT_MIN_CONNECTION_MINUTES = 75


def calculate_connection_buffer(
    arriving_segment: FlightSegment,
    departing_segment: FlightSegment,
) -> int:
    """Returns available connection time in minutes between two segments."""
    arrival  = arriving_segment.estimated_arrival or arriving_segment.scheduled_arrival
    departure = departing_segment.scheduled_departure
    return int((departure - arrival).total_seconds() / 60)


def is_connection_viable(
    arriving_segment: FlightSegment,
    departing_segment: FlightSegment,
    min_buffer_minutes: int = DEFAULT_MIN_CONNECTION_MINUTES,
) -> bool:
    buffer = calculate_connection_buffer(arriving_segment, departing_segment)
    return buffer >= min_buffer_minutes


def analyze_trip_impact(trip: Trip, min_connection_minutes: int = DEFAULT_MIN_CONNECTION_MINUTES) -> Dict[str, Any]:
    """
    Walks the flight segment dependency chain and identifies all
    downstream impacts from updated estimated arrivals.

    Returns a structured impact report used by the recovery agent.
    """
    segments: List[FlightSegment] = sorted(trip.flight_segments, key=lambda s: s.sequence_order)
    impacts = []
    connection_broken = False
    broken_at_segment = None

    # Check each consecutive pair of segments for connection viability
    for i in range(len(segments) - 1):
        inbound  = segments[i]
        outbound = segments[i + 1]

        buffer = calculate_connection_buffer(inbound, outbound)
        viable = buffer >= min_connection_minutes

        impact_entry = {
            "inbound_flight":  inbound.flight_number,
            "outbound_flight": outbound.flight_number,
            "connection_airport": inbound.destination_airport,
            "available_buffer_minutes": buffer,
            "min_required_minutes": min_connection_minutes,
            "connection_viable": viable,
        }

        if not viable and not connection_broken:
            connection_broken = True
            broken_at_segment = outbound
            impact_entry["status"] = "MISSED_CONNECTION"
            impact_entry["severity"] = "CRITICAL"
        elif not viable:
            impact_entry["status"] = "ALSO_AFFECTED"
        else:
            impact_entry["status"] = "OK"

        impacts.append(impact_entry)

    # Calculate final arrival at destination
    last_segment = segments[-1]
    final_arrival = last_segment.estimated_arrival or last_segment.scheduled_arrival

    # Assess downstream services
    downstream = []

    for transfer in trip.transfers:
        pickup = transfer.pickup_time
        if final_arrival > pickup:
            gap = int((final_arrival - pickup).total_seconds() / 60)
            downstream.append({
                "type": "TRANSFER",
                "id": transfer.id,
                "status": "INVALID",
                "reason": f"Flight arrives {gap} minutes after scheduled pickup",
                "original_pickup": pickup.isoformat(),
                "new_arrival": final_arrival.isoformat(),
            })
        else:
            downstream.append({"type": "TRANSFER", "id": transfer.id, "status": "OK"})

    for hotel in trip.hotel_bookings:
        check_in = hotel.check_in_date
        # if arrival is next day or significantly late, hotel may need adjustment
        if final_arrival.date() > check_in.date():
            downstream.append({
                "type": "HOTEL",
                "id": hotel.id,
                "status": "DATE_MISMATCH",
                "reason": f"Arrival date {final_arrival.date()} after check-in date {check_in.date()}",
                "action_needed": "MODIFY_CHECK_IN",
            })
        else:
            late_hour = int(hotel.latest_check_in.split(":")[0])
            if final_arrival.hour > late_hour:
                downstream.append({
                    "type": "HOTEL",
                    "id": hotel.id,
                    "status": "LATE_ARRIVAL",
                    "reason": f"Expected arrival {final_arrival.strftime('%H:%M')} after latest check-in {hotel.latest_check_in}",
                    "action_needed": "NOTIFY_HOTEL",
                })
            else:
                downstream.append({"type": "HOTEL", "id": hotel.id, "status": "OK"})

    delayed_segment = max(segments, key=lambda s: s.delay_minutes or 0)
    delay = delayed_segment.delay_minutes or 0

    return {
        "trip_id":           trip.id,
        "connection_broken": connection_broken,
        "broken_at":         broken_at_segment.flight_number if broken_at_segment else None,
        "missed_flight":     broken_at_segment.flight_number if broken_at_segment else None,
        "delay_minutes":     delay,
        "final_arrival":     final_arrival.isoformat(),
        "connection_impacts": impacts,
        "downstream_impacts": downstream,
        "recovery_needed":   connection_broken or any(d["status"] != "OK" for d in downstream),
    }
