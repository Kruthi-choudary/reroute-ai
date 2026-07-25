from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import hashlib, json

from app.database import get_db
from app.models import DisruptionEvent, DisruptionType, DisruptionSeverity, FlightSegment

router = APIRouter()


class DisruptionIn(BaseModel):
    trip_id:           int
    flight_segment_id: int
    disruption_type:   DisruptionType
    severity:          DisruptionSeverity = DisruptionSeverity.HIGH
    new_estimated_arrival: Optional[datetime] = None
    new_estimated_departure: Optional[datetime] = None
    description:       Optional[str] = None


@router.post("/", status_code=201)
def report_disruption(data: DisruptionIn, db: Session = Depends(get_db)):
    segment = db.query(FlightSegment).filter(FlightSegment.id == data.flight_segment_id).first()
    if not segment:
        raise HTTPException(404, "Flight segment not found")

    # idempotency key — same disruption on same segment won't be processed twice
    key_data = f"{data.trip_id}:{data.flight_segment_id}:{data.disruption_type}:{data.new_estimated_arrival}"
    idempotency_key = hashlib.sha256(key_data.encode()).hexdigest()

    existing = db.query(DisruptionEvent).filter(
        DisruptionEvent.idempotency_key == idempotency_key
    ).first()
    if existing:
        return {"id": existing.id, "message": "Disruption already recorded", "duplicate": True}

    previous_state = {
        "estimated_arrival":   segment.estimated_arrival.isoformat() if segment.estimated_arrival else None,
        "estimated_departure": segment.estimated_departure.isoformat() if segment.estimated_departure else None,
        "status":              segment.status.value,
        "delay_minutes":       segment.delay_minutes,
    }

    # update segment with new estimates
    if data.new_estimated_arrival:
        delay = int((data.new_estimated_arrival - segment.scheduled_arrival).total_seconds() / 60)
        segment.estimated_arrival = data.new_estimated_arrival
        segment.delay_minutes = max(0, delay)
        segment.status = "DELAYED"

    if data.new_estimated_departure:
        segment.estimated_departure = data.new_estimated_departure

    new_state = {
        "estimated_arrival":   segment.estimated_arrival.isoformat() if segment.estimated_arrival else None,
        "estimated_departure": segment.estimated_departure.isoformat() if segment.estimated_departure else None,
        "status":              segment.status if isinstance(segment.status, str) else segment.status.value,
        "delay_minutes":       segment.delay_minutes,
    }

    event = DisruptionEvent(
        trip_id=data.trip_id,
        flight_segment_id=data.flight_segment_id,
        idempotency_key=idempotency_key,
        disruption_type=data.disruption_type,
        severity=data.severity,
        previous_state=previous_state,
        new_state=new_state,
        description=data.description,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return {"id": event.id, "idempotency_key": idempotency_key, "message": "Disruption recorded"}


@router.get("/{trip_id}")
def get_disruptions(trip_id: int, db: Session = Depends(get_db)):
    return db.query(DisruptionEvent).filter(DisruptionEvent.trip_id == trip_id).all()
