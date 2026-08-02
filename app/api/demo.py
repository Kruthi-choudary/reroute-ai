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
    HotelBooking, Transfer, TripStatus, FlightStatus, DisruptionType, DisruptionSeverity,
    HotelNotificationStatus,
)

router = APIRouter(dependencies=[Depends(_verify_demo_secret)])

DEMO_USER_ID = 1


@router.post("/seed")
def seed_demo(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Creates the demo HYD→DXB→LHR trip in a HEALTHY state. Call once before the demo.
    Pass ?user_id=X to seed for a specific user (e.g. the one who signed up via the frontend).
    """
    # Use the first user in the DB if no user_id provided
    target_user = None
    if user_id:
        target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        target_user = db.query(User).order_by(User.id).first()

    if target_user:
        # User exists — check if they already have a trip
        trip = db.query(Trip).filter(Trip.user_id == target_user.id).first()
        if trip:
            return {"message": "Already seeded", "trip_id": trip.id, "user_id": target_user.id}
        # User exists but no trip — create trip for them
        target_user_id = target_user.id
    else:
        # No users at all — create the demo user
        user = User(email="demo@reroute.ai", name="Demo Traveler", phone="+91-9999999999")
        db.add(user)
        db.flush()
        target_user_id = user.id
        db.add(TravelerPreference(user_id=target_user_id, preferred_airlines=["EK", "BA"], preferred_cabin="ECONOMY"))
        db.add(PolicyRule(user_id=target_user_id, auto_spend_limit=150.0, approval_spend_limit=500.0, max_spend_limit=1000.0))

    base = datetime(2026, 8, 15)
    trip = Trip(
        user_id=target_user_id,
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

    # Hotel: same day check-in — LHR → The Strand Palace Hotel
    checkin  = base.replace(hour=20, minute=0)   # matches transfer arrival time
    checkout = checkin.replace(hour=12) + timedelta(days=3)
    db.add(HotelBooking(
        trip_id=trip.id,
        property_name="The Strand Palace Hotel",
        city="London",
        hotel_email="reservations@strandpalace.demo",
        check_in_date=checkin,
        check_out_date=checkout,
        original_check_in_date=checkin,
        original_check_out_date=checkout,
        booking_reference="HTL-LON-001",
        earliest_check_in="14:00",
        latest_check_in="23:59",
        status="CONFIRMED",
        notification_status=HotelNotificationStatus.PENDING,
    ))

    db.commit()
    return {"message": "Demo seeded", "trip_id": trip.id, "user_id": target_user_id}


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

    # Guard: don't start a second pipeline if one is already running for this trip
    from app.models import RecoveryPlan
    existing_plan = db.query(RecoveryPlan).filter(RecoveryPlan.trip_id == trip_id).first()
    if existing_plan and existing_plan.status.value not in ("COMPLETED", "FAILED"):
        return {
            "message": "Recovery already in progress",
            "disruption_id": disruption_id,
            "plan_id": existing_plan.id,
            "plan_status": existing_plan.status.value,
        }

    # Kick off the full recovery pipeline asynchronously
    background_tasks.add_task(start_recovery, trip_id, disruption_id)

    return {
        "message": "Disruption injected — recovery pipeline started",
        "disruption_id": disruption_id,
        "delay_minutes": delay_minutes,
        "new_arrival": new_arrival.isoformat(),
    }


@router.post("/reset")
def reset_demo(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Resets the demo trip back to HEALTHY so you can run it again."""
    from app.models import RecoveryPlan, RecoveryAction, DisruptionEvent, AuditLog, Notification

    target_uid = user_id if user_id is not None else DEMO_USER_ID
    trip = db.query(Trip).filter(Trip.user_id == target_uid).first()
    if not trip:
        return {"error": "Demo not seeded yet"}

    # wipe recovery data — use explicit object deletion to avoid SQLAlchemy bulk-delete sync issues
    for plan in db.query(RecoveryPlan).filter(RecoveryPlan.trip_id == trip.id).all():
        for action in db.query(RecoveryAction).filter(RecoveryAction.recovery_plan_id == plan.id).all():
            db.delete(action)
        db.delete(plan)
    db.flush()
    db.query(DisruptionEvent).filter(DisruptionEvent.trip_id == trip.id).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.trip_id == trip.id).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.trip_id == trip.id).delete(synchronize_session=False)

    # reset flight segments to original schedule
    segments = db.query(FlightSegment).filter(FlightSegment.trip_id == trip.id).all()
    for seg in segments:
        seg.status = FlightStatus.SCHEDULED
        seg.delay_minutes = 0
        seg.estimated_departure = seg.scheduled_departure
        seg.estimated_arrival = seg.scheduled_arrival

    trip.status = TripStatus.HEALTHY

    # reset hotel reservation back to original state
    hotel = db.query(HotelBooking).filter(HotelBooking.trip_id == trip.id).first()
    if hotel:
        hotel.status = "CONFIRMED"
        hotel.notification_status = HotelNotificationStatus.PENDING
        hotel.notified_at = None
        if hotel.original_check_in_date:
            hotel.check_in_date = hotel.original_check_in_date
        if hotel.original_check_out_date:
            hotel.check_out_date = hotel.original_check_out_date

    db.commit()

    # Tell the frontend to clear its recovery cache
    from app.services.websocket import broadcast
    broadcast(trip.id, {"event": "TRIP_RESET", "trip_id": trip.id})

    return {"message": "Demo reset to HEALTHY", "trip_id": trip.id}
