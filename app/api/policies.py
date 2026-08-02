from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models import PolicyRule, TravelerPreference

router = APIRouter()


class PolicyUpdate(BaseModel):
    auto_spend_limit:     Optional[float] = None
    approval_spend_limit: Optional[float] = None
    max_spend_limit:      Optional[float] = None
    allowed_cabins:       Optional[List[str]] = None
    prohibited_airports:  Optional[List[str]] = None
    require_same_airline: Optional[bool] = None


class PreferenceUpdate(BaseModel):
    preferred_airlines: Optional[List[str]] = None
    preferred_cabin:    Optional[str] = None
    max_stops:          Optional[int] = None
    seat_preference:    Optional[str] = None


@router.get("/{user_id}")
def get_policy(user_id: int, db: Session = Depends(get_db)):
    policy = db.query(PolicyRule).filter(PolicyRule.user_id == user_id).first()
    if not policy:
        # Auto-create with sensible defaults on first access
        policy = PolicyRule(
            user_id=user_id,
            auto_spend_limit=50.0,
            approval_spend_limit=500.0,
            max_spend_limit=1000.0,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


@router.put("/{user_id}")
def update_policy(user_id: int, data: PolicyUpdate, db: Session = Depends(get_db)):
    policy = db.query(PolicyRule).filter(PolicyRule.user_id == user_id).first()
    if not policy:
        policy = PolicyRule(user_id=user_id)
        db.add(policy)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(policy, field, value)

    db.commit()
    db.refresh(policy)
    return policy


@router.get("/{user_id}/preferences")
def get_preferences(user_id: int, db: Session = Depends(get_db)):
    pref = db.query(TravelerPreference).filter(TravelerPreference.user_id == user_id).first()
    if not pref:
        # Auto-create with sensible defaults on first access
        pref = TravelerPreference(
            user_id=user_id,
            preferred_cabin="ECONOMY",
            seat_preference="WINDOW",
            preferred_airlines=[],
        )
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


@router.put("/{user_id}/preferences")
def update_preferences(user_id: int, data: PreferenceUpdate, db: Session = Depends(get_db)):
    pref = db.query(TravelerPreference).filter(TravelerPreference.user_id == user_id).first()
    if not pref:
        pref = TravelerPreference(user_id=user_id)
        db.add(pref)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(pref, field, value)

    db.commit()
    db.refresh(pref)
    return pref
