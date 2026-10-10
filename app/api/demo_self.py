"""
Self-serve demo endpoints for the in-app "Simulate disruption" button.

Unlike app/api/demo.py (open, DEMO_SECRET-gated — meant for curl/local testing),
these are scoped to the authenticated caller via the normal JWT dependency, so
they're safe to expose publicly: a visitor can only ever seed/disrupt/reset
their own trip, never anyone else's.
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.demo import _seed_trip_for_user, _inject_disruption, _reset_trip_to_healthy
from app.core.auth import get_current_user
from app.database import get_db
from app.models import Trip, User

router = APIRouter()


@router.post("/seed")
def seed_my_demo_trip(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip_id = _seed_trip_for_user(db, current_user.id)
    return {"trip_id": trip_id}


@router.post("/disrupt")
def disrupt_my_trip(
    delay_minutes: int = 165,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip_id = _seed_trip_for_user(db, current_user.id)
    return _inject_disruption(db, background_tasks, trip_id, delay_minutes)


@router.post("/reset")
def reset_my_trip(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    trip = db.query(Trip).filter(Trip.user_id == current_user.id).first()
    if not trip:
        return {"error": "No trip to reset"}
    _reset_trip_to_healthy(db, trip)
    return {"message": "Reset to healthy", "trip_id": trip.id}
