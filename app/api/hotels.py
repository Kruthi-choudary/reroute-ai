from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import HotelBooking, Trip, User

router = APIRouter()


@router.get("/")
def list_hotel_reservations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip_ids = [t.id for t in db.query(Trip.id).filter(Trip.user_id == current_user.id).all()]
    if not trip_ids:
        return []
    reservations = (
        db.query(HotelBooking)
        .filter(HotelBooking.trip_id.in_(trip_ids))
        .order_by(HotelBooking.check_in_date.asc())
        .all()
    )
    return [_serialize(r) for r in reservations]


@router.get("/{reservation_id}")
def get_hotel_reservation(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = db.query(HotelBooking).filter(HotelBooking.id == reservation_id).first()
    if not r:
        raise HTTPException(404, "Reservation not found")
    # Ownership check — ensure this reservation belongs to the requesting user
    trip = db.query(Trip).filter(Trip.id == r.trip_id, Trip.user_id == current_user.id).first()
    if not trip:
        raise HTTPException(403, "Access denied")
    return _serialize(r)


def _serialize(r: HotelBooking) -> dict:
    return {
        "id":                      r.id,
        "trip_id":                 r.trip_id,
        "property_name":           r.property_name,
        "city":                    r.city,
        "hotel_email":             r.hotel_email,
        "check_in_date":           r.check_in_date.isoformat() if r.check_in_date else None,
        "check_out_date":          r.check_out_date.isoformat() if r.check_out_date else None,
        "original_check_in_date":  r.original_check_in_date.isoformat() if r.original_check_in_date else None,
        "original_check_out_date": r.original_check_out_date.isoformat() if r.original_check_out_date else None,
        "booking_reference":       r.booking_reference,
        "status":                  r.status,
        "notification_status":     r.notification_status.value if r.notification_status else "PENDING",
        "notified_at":             r.notified_at.isoformat() if r.notified_at else None,
    }
