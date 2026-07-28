from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.models import User, TravelerPreference, PolicyRule
from app.core.auth import hash_password, verify_password, create_token

router = APIRouter()


class RegisterIn(BaseModel):
    email:    str
    name:     str
    password: str
    phone:    Optional[str] = None


class LoginIn(BaseModel):
    email:    str
    password: str


def _token_response(user: User) -> dict:
    return {
        "token": create_token(user.id),
        "id":    user.id,
        "email": user.email,
        "name":  user.name,
    }


@router.post("/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already registered")

    user = User(
        email=data.email,
        name=data.name,
        phone=data.phone,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.flush()

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
    return _token_response(user)


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return _token_response(user)
