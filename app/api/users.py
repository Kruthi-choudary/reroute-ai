from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User, TravelerPreference, PolicyRule

router = APIRouter()


class UserCreate(BaseModel):
    email: str
    name:  str
    phone: Optional[str] = None


@router.post("/", status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(400, f"User with email {data.email} already exists")

    user = User(email=data.email, name=data.name, phone=data.phone)
    db.add(user)
    db.flush()

    # create default policy and preferences for every new user
    db.add(PolicyRule(
        user_id=user.id,
        auto_spend_limit=150.0,
        approval_spend_limit=500.0,
        max_spend_limit=1000.0,
        allowed_cabins=["ECONOMY", "PREMIUM_ECONOMY"],
        prohibited_airports=[],
        require_same_airline=False,
    ))
    db.add(TravelerPreference(
        user_id=user.id,
        preferred_airlines=[],
        preferred_cabin="ECONOMY",
        max_stops=1,
    ))

    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@router.get("/me")
def get_current_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return {
        "id":          current_user.id,
        "email":       current_user.email,
        "name":        current_user.name,
        "phone":       current_user.phone,
        "preferences": current_user.preferences,
        "policy":      current_user.policy,
        "trips":       [{"id": t.id, "name": t.name, "status": t.status} for t in current_user.trips],
    }
