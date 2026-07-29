from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models import Trip, FlightSegment, HotelBooking, Transfer, TripStatus, FlightStatus

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class FlightSegmentIn(BaseModel):
    sequence_order:      int
    flight_number:       str
    airline:             str
    origin_airport:      str
    destination_airport: str
    scheduled_departure: datetime
    scheduled_arrival:   datetime
    cabin_class:         str = "ECONOMY"
    booking_reference:   Optional[str] = None

class HotelBookingIn(BaseModel):
    property_name:     str
    city:              str
    check_in_date:     datetime
    check_out_date:    datetime
    booking_reference: Optional[str] = None
    earliest_check_in: str = "14:00"
    latest_check_in:   str = "23:59"

class TransferIn(BaseModel):
    pickup_location:   str
    pickup_time:       datetime
    destination:       str
    booking_reference: Optional[str] = None

class TripCreate(BaseModel):
    user_id:        int
    name:           str
    origin:         str
    destination:    str
    departure_date: datetime
    return_date:    Optional[datetime] = None
    flights:        List[FlightSegmentIn]
    hotels:         List[HotelBookingIn] = []
    transfers:      List[TransferIn]     = []


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/")
def list_trips(user_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Trip).options(joinedload(Trip.flight_segments))
    if user_id:
        q = q.filter(Trip.user_id == user_id)
    trips = q.order_by(Trip.created_at.desc()).limit(50).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "origin": t.origin,
            "destination": t.destination,
            "departure_date": t.departure_date,
            "status": t.status,
            "flights": t.flight_segments,
        }
        for t in trips
    ]


@router.get("/{trip_id}")
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(404, "Trip not found")
    return {
        "id":             trip.id,
        "name":           trip.name,
        "origin":         trip.origin,
        "destination":    trip.destination,
        "departure_date": trip.departure_date,
        "status":         trip.status,
        "flights":        trip.flight_segments,
        "hotels":         trip.hotel_bookings,
        "transfers":      trip.transfers,
    }


@router.post("/", status_code=201)
def create_trip(data: TripCreate, db: Session = Depends(get_db)):
    trip = Trip(
        user_id=data.user_id,
        name=data.name,
        origin=data.origin,
        destination=data.destination,
        departure_date=data.departure_date,
        return_date=data.return_date,
        status=TripStatus.HEALTHY,
    )
    db.add(trip)
    db.flush()

    for f in data.flights:
        db.add(FlightSegment(
            trip_id=trip.id,
            sequence_order=f.sequence_order,
            flight_number=f.flight_number,
            airline=f.airline,
            origin_airport=f.origin_airport,
            destination_airport=f.destination_airport,
            scheduled_departure=f.scheduled_departure,
            scheduled_arrival=f.scheduled_arrival,
            estimated_departure=f.scheduled_departure,
            estimated_arrival=f.scheduled_arrival,
            cabin_class=f.cabin_class,
            booking_reference=f.booking_reference,
            status=FlightStatus.SCHEDULED,
        ))

    for h in data.hotels:
        db.add(HotelBooking(
            trip_id=trip.id,
            property_name=h.property_name,
            city=h.city,
            check_in_date=h.check_in_date,
            check_out_date=h.check_out_date,
            booking_reference=h.booking_reference,
            earliest_check_in=h.earliest_check_in,
            latest_check_in=h.latest_check_in,
        ))

    for t in data.transfers:
        db.add(Transfer(
            trip_id=trip.id,
            pickup_location=t.pickup_location,
            pickup_time=t.pickup_time,
            destination=t.destination,
            booking_reference=t.booking_reference,
        ))

    db.commit()
    db.refresh(trip)
    return {"id": trip.id, "status": trip.status, "message": "Trip created"}
