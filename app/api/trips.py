from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

import hashlib
from datetime import timedelta

from app.core.auth import get_current_user
from app.database import get_db
from app.models import Trip, FlightSegment, HotelBooking, Transfer, TripStatus, FlightStatus, User, HotelNotificationStatus

# Destination airport code → (hotel name, demo email)
_DESTINATION_HOTELS: dict[str, tuple[str, str]] = {
    "LHR": ("The Strand Palace Hotel",      "reservations@strandpalace.demo"),
    "LGW": ("The Lalit London",             "reservations@lalitlondon.demo"),
    "DXB": ("Burj Al Nour",                 "reservations@burjalnour.demo"),
    "AUH": ("Emirates Palace",              "reservations@emiratespalace.demo"),
    "ZRH": ("Widder Hotel",                 "reservations@widderhotel.demo"),
    "CDG": ("Le Meurice",                   "reservations@lemeurice.demo"),
    "ORY": ("Hôtel de Crillon",             "reservations@crillon.demo"),
    "HND": ("The Peninsula Tokyo",          "reservations@peninsula-tokyo.demo"),
    "NRT": ("Park Hyatt Tokyo",             "reservations@parkhyatt-tokyo.demo"),
    "SIN": ("Marina Bay Sands",             "reservations@marinabaysands.demo"),
    "SYD": ("Park Hyatt Sydney",            "reservations@parkhyatt-sydney.demo"),
    "GRU": ("Fasano São Paulo",             "reservations@fasano.demo"),
    "JFK": ("The Plaza",                    "reservations@theplaza.demo"),
    "LAX": ("Shutters on the Beach",        "reservations@shutters.demo"),
    "ORD": ("The Langham Chicago",          "reservations@langham-chicago.demo"),
    "SFO": ("Fairmont San Francisco",       "reservations@fairmont-sf.demo"),
    "MIA": ("Faena Hotel Miami",            "reservations@faena.demo"),
    "BRU": ("Hotel Amigo",                  "reservations@hotelamigo.demo"),
    "FRA": ("Steigenberger Frankfurter Hof","reservations@sfh.demo"),
    "AMS": ("Conservatorium Hotel",         "reservations@conservatorium.demo"),
    "MAD": ("Hotel Ritz Madrid",            "reservations@ritz-madrid.demo"),
    "BCN": ("Hotel Arts Barcelona",         "reservations@hotelarts.demo"),
    "FCO": ("Hotel de Russie",              "reservations@hotelderussie.demo"),
    "MXP": ("Four Seasons Milan",           "reservations@fourseasons-milan.demo"),
    "ICN": ("Four Seasons Seoul",           "reservations@fourseasons-seoul.demo"),
    "BOM": ("The Taj Mahal Palace",         "reservations@tajmahalpalace.demo"),
    "DEL": ("The Leela Palace",             "reservations@leela-delhi.demo"),
    "HYD": ("The Westin Hyderabad",         "reservations@westin-hyd.demo"),
    "BLR": ("The Leela Palace Bengaluru",   "reservations@leela-blr.demo"),
}


def _hotel_for_destination(code: str) -> tuple[str, str]:
    return _DESTINATION_HOTELS.get(
        code,
        (f"Grand Hotel {code}", f"reservations@grandhotel-{code.lower()}.demo"),
    )


def _booking_ref(trip_id: int, hotel_name: str) -> str:
    h = hashlib.md5(f"{trip_id}-{hotel_name}".encode()).hexdigest()[:6].upper()
    return f"HTL-{h}"

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
def list_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trips = (
        db.query(Trip)
        .options(joinedload(Trip.flight_segments))
        .filter(Trip.user_id == current_user.id)
        .order_by(Trip.created_at.desc())
        .limit(50)
        .all()
    )
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
def get_trip(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == current_user.id).first()
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

    if data.hotels:
        for h in data.hotels:
            db.add(HotelBooking(
                trip_id=trip.id,
                property_name=h.property_name,
                city=h.city,
                check_in_date=h.check_in_date,
                check_out_date=h.check_out_date,
                original_check_in_date=h.check_in_date,
                original_check_out_date=h.check_out_date,
                booking_reference=h.booking_reference,
                earliest_check_in=h.earliest_check_in,
                latest_check_in=h.latest_check_in,
                notification_status=HotelNotificationStatus.PENDING,
            ))
    else:
        # Auto-create a hotel reservation based on the destination
        hotel_name, hotel_email = _hotel_for_destination(data.destination)
        # check-in = last flight arrival (if provided), else departure_date + 1 day
        last_flight = sorted(data.flights, key=lambda f: f.sequence_order)[-1] if data.flights else None
        checkin  = last_flight.scheduled_arrival if last_flight else data.departure_date + timedelta(days=1)
        checkout = checkin + timedelta(days=3)
        ref = _booking_ref(trip.id, hotel_name)
        db.add(HotelBooking(
            trip_id=trip.id,
            property_name=hotel_name,
            city=data.destination,
            hotel_email=hotel_email,
            check_in_date=checkin,
            check_out_date=checkout,
            original_check_in_date=checkin,
            original_check_out_date=checkout,
            booking_reference=ref,
            earliest_check_in="14:00",
            latest_check_in="23:59",
            status="CONFIRMED",
            notification_status=HotelNotificationStatus.PENDING,
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
