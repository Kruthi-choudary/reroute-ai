from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Notification

router = APIRouter()


@router.get("/{user_id}")
def get_notifications(user_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
