import os
from fastapi import APIRouter, Depends, BackgroundTasks, Header, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_db

_DEMO_SECRET = os.getenv("DEMO_SECRET", "")


def _verify_demo_secret(x_demo_secret: str = Header(default="")):
    if _DEMO_SECRET and x_demo_secret != _DEMO_SECRET:
        raise HTTPException(403, "Invalid demo secret")
from app.models import (
    User, TravelerPreference, PolicyRule, Trip, FlightSegment,
    HotelBooking, Transfer, TripStatus, FlightStatus, DisruptionType, DisruptionSeverity
)

router = APIRouter(dependencies=[Depends(_verify_demo_secret)])

DEMO_USER_ID = 1


@router.post("/seed")
def seed_demo(db: Session = Depends(get_db)):
    """Creates the demo HYD→DXB→LHR trip in a HEALTHY state. Call once before the demo."""

    # idempotent — skip if already seeded
    existing = db.query(User).filter(User.id == DEMO_USER_ID).first()
    if existing:
        trip = db.query(Trip).filter(Trip.user_id == DEMO_USER_ID).first()
        return {"message": "Already seeded", "trip_id": trip.id if trip else None}

    user = User(id=DEMO_USER_ID, email="demo@reroute.ai", name="Demo Traveler", phone="+91-9999999999")
    db.add(user)
    db.flush()

    db.add(TravelerPreference(user_id=DEMO_USER_ID, preferred_airlines=["EK", "BA"], preferred_cabin="ECONOMY"))
    db.add(PolicyRule(user_id=DEMO_USER_ID, auto_spend_limit=150.0, approval_spend_limit=500.0, max_spend_limit=1000.0))

    base = datetime(2026, 8, 15)
    trip = Trip(
        user_id=DEMO_USER_ID,
        name="London Business Trip",
        origin="HYD",
        destination="LHR",
        departure_date=base,
        status=TripStatus.HEALTHY,
    )
    db.add(trip)
    db.flush()

    # HYD → DXB  10:00 → 12:30
    db.add(FlightSegment(
        trip_id=trip.id, sequence_order=1,
        flight_number="EK527", airline="EK",
        origin_airport="HYD", destination_airport="DXB",
        scheduled_departure=base.replace(hour=10, minute=0),
        scheduled_arrival=base.replace(hour=12, minute=30),
        estimated_departure=base.replace(hour=10, minute=0),
        estimated_arrival=base.replace(hour=12, minute=30),
        cabin_class="ECONOMY", booking_reference="EK-HYD-001",
        price_usd=180.0,
        status=FlightStatus.SCHEDULED,
    ))

    # DXB → LHR  14:00 → 18:30
    db.add(FlightSegment(
        trip_id=trip.id, sequence_order=2,
        flight_number="EK003", airline="EK",
        origin_airport="DXB", destination_airport="LHR",
        scheduled_departure=base.replace(hour=14, minute=0),
        scheduled_arrival=base.replace(hour=18, minute=30),
        estimated_departure=base.replace(hour=14, minute=0),
        estimated_arrival=base.replace(hour=18, minute=30),
        cabin_class="ECONOMY", booking_reference="EK-DXB-002",
        price_usd=300.0,
        status=FlightStatus.SCHEDULED,
    ))

    # Transfer: LHR → Hotel at 20:00
    db.add(Transfer(
        trip_id=trip.id,
        pickup_location="LHR Terminal 2",
        pickup_time=base.replace(hour=20, minute=0),
        destination="The Strand Palace Hotel, London",
        booking_reference="TRANS-LHR-001",
        status="CONFIRMED",
    ))

    # Hotel: same day check-in
    db.add(HotelBooking(
        trip_id=trip.id,
        property_name="The Strand Palace Hotel",
        city="London",
        check_in_date=base,
        check_out_date=base + timedelta(days=3),
        booking_reference="HTL-LON-001",
        earliest_check_in="14:00",
        latest_check_in="23:59",
    ))

    db.commit()
    return {"message": "Demo seeded", "trip_id": trip.id, "user_id": DEMO_USER_ID}


@router.post("/disruption")
def inject_disruption(
    trip_id: int,
    delay_minutes: int = 165,
    segment_id: Optional[int] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """
    Injects a disruption into any trip segment.
    segment_id: which segment to delay (defaults to the first segment if not specified).
    This feeds the REAL recovery pipeline — nothing is mocked.
    """
    from app.api.disruptions import DisruptionIn, report_disruption
    from app.core.recovery_orchestrator import start_recovery

    if segment_id:
        segment = db.query(FlightSegment).filter(
            FlightSegment.id == segment_id,
            FlightSegment.trip_id == trip_id,
        ).first()
    else:
        segment = (
            db.query(FlightSegment)
            .filter(FlightSegment.trip_id == trip_id)
            .order_by(FlightSegment.sequence_order)
            .first()
        )

    if not segment:
        return {"error": "Flight segment not found for this trip"}

    new_arrival = segment.scheduled_arrival + timedelta(minutes=delay_minutes)

    disruption_data = DisruptionIn(
        trip_id=trip_id,
        flight_segment_id=segment.id,
        disruption_type=DisruptionType.DELAY,
        severity=DisruptionSeverity.CRITICAL,
        new_estimated_arrival=new_arrival,
        description=f"{segment.flight_number} delayed by {delay_minutes} minutes — {segment.destination_airport} arrival now {new_arrival.strftime('%H:%M')}",
    )

    result = report_disruption(disruption_data, db)
    disruption_id = result["id"]

    # Kick off the full recovery pipeline asynchronously
    background_tasks.add_task(start_recovery, trip_id, disruption_id)

    return {
        "message": "Disruption injected — recovery pipeline started",
        "disruption_id": disruption_id,
        "delay_minutes": delay_minutes,
        "new_arrival": new_arrival.isoformat(),
    }


@router.post("/reset")
def reset_demo(db: Session = Depends(get_db)):
    """Resets the demo trip back to HEALTHY so you can run it again."""
    from app.models import RecoveryPlan, RecoveryAction, DisruptionEvent, AuditLog, Notification

    trip = db.query(Trip).filter(Trip.user_id == DEMO_USER_ID).first()
    if not trip:
        return {"error": "Demo not seeded yet"}

    # wipe recovery data
    for plan in db.query(RecoveryPlan).filter(RecoveryPlan.trip_id == trip.id).all():
        db.query(RecoveryAction).filter(RecoveryAction.recovery_plan_id == plan.id).delete()
    db.query(RecoveryPlan).filter(RecoveryPlan.trip_id == trip.id).delete()
    db.query(DisruptionEvent).filter(DisruptionEvent.trip_id == trip.id).delete()
    db.query(AuditLog).filter(AuditLog.trip_id == trip.id).delete()
    db.query(Notification).filter(Notification.trip_id == trip.id).delete()

    # reset flight segments to original schedule
    segments = db.query(FlightSegment).filter(FlightSegment.trip_id == trip.id).all()
    for seg in segments:
        seg.status = FlightStatus.SCHEDULED
        seg.delay_minutes = 0
        seg.estimated_departure = seg.scheduled_departure
        seg.estimated_arrival = seg.scheduled_arrival

    trip.status = TripStatus.HEALTHY
    db.commit()

    return {"message": "Demo reset to HEALTHY", "trip_id": trip.id}
