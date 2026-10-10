from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import RecoveryPlan, Trip, User

router = APIRouter()


def _owned_plan_query(db: Session, current_user: User):
    return (
        db.query(RecoveryPlan)
        .join(Trip, Trip.id == RecoveryPlan.trip_id)
        .filter(Trip.user_id == current_user.id)
    )


@router.get("/{trip_id}")
def get_recovery_state(
    trip_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = (
        _owned_plan_query(db, current_user)
        .filter(RecoveryPlan.trip_id == trip_id)
        .order_by(RecoveryPlan.created_at.desc())
        .first()
    )
    if not plan:
        raise HTTPException(404, "No recovery plan found for this trip")
    return {
        "id":               plan.id,
        "trip_id":          plan.trip_id,
        "status":           plan.status,
        "policy_decision":  plan.policy_decision,
        "total_extra_cost": plan.total_extra_cost,
        "reasoning":        plan.reasoning,
        "selected_flight":  plan.selected_flight,
        "actions":          plan.actions,
    }


@router.get("/{plan_id}/alternatives")
def get_alternatives(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = _owned_plan_query(db, current_user).filter(RecoveryPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Recovery plan not found")
    # alternatives stored in selected_flight JSON during scoring phase
    return {"plan_id": plan_id, "alternatives": plan.selected_flight or []}


@router.post("/{plan_id}/approve")
def approve_recovery(
    plan_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.recovery_orchestrator import execute_recovery_plan
    plan = _owned_plan_query(db, current_user).filter(RecoveryPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Recovery plan not found")
    if plan.status.value != "AWAITING_APPROVAL":
        raise HTTPException(400, f"Plan is not awaiting approval (current: {plan.status})")

    background_tasks.add_task(execute_recovery_plan, plan_id)
    return {"message": "Recovery approved, executing...", "plan_id": plan_id}


@router.post("/{plan_id}/reject")
def reject_recovery(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models import RecoveryPlanStatus
    plan = _owned_plan_query(db, current_user).filter(RecoveryPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Recovery plan not found")
    plan.status = RecoveryPlanStatus.FAILED
    db.commit()
    return {"message": "Recovery plan rejected", "plan_id": plan_id}
