from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.core.auth import get_current_user
from app.database import get_db
from app.models import PolicyRule, TravelerPreference, User

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


@router.get("/")
def get_policy(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    policy = db.query(PolicyRule).filter(PolicyRule.user_id == current_user.id).first()
    if not policy:
        # Auto-create with sensible defaults on first access
        policy = PolicyRule(
            user_id=current_user.id,
            auto_spend_limit=50.0,
            approval_spend_limit=500.0,
            max_spend_limit=1000.0,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
    return policy


@router.put("/")
def update_policy(data: PolicyUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    policy = db.query(PolicyRule).filter(PolicyRule.user_id == current_user.id).first()
    if not policy:
        policy = PolicyRule(user_id=current_user.id)
        db.add(policy)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(policy, field, value)

    db.commit()
    db.refresh(policy)
    return policy


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pref = db.query(TravelerPreference).filter(TravelerPreference.user_id == current_user.id).first()
    if not pref:
        # Auto-create with sensible defaults on first access
        pref = TravelerPreference(
            user_id=current_user.id,
            preferred_cabin="ECONOMY",
            seat_preference="WINDOW",
            preferred_airlines=[],
        )
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


@router.put("/preferences")
def update_preferences(data: PreferenceUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    pref = db.query(TravelerPreference).filter(TravelerPreference.user_id == current_user.id).first()
    if not pref:
        pref = TravelerPreference(user_id=current_user.id)
        db.add(pref)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(pref, field, value)

    db.commit()
    db.refresh(pref)
    return pref
