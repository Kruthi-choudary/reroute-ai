"""
Recovery Orchestrator — coordinates the full recovery pipeline.
Called as a background task after a disruption event is created.
"""
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Trip, FlightSegment, DisruptionEvent, RecoveryPlan, RecoveryAction,
    AuditLog, Notification, TripStatus, RecoveryPlanStatus, PolicyDecision,
    ActionType, ActionStatus, AuditActor, NotificationChannel, FlightStatus
)
from app.core.impact import analyze_trip_impact
from app.core.scoring import rank_alternatives, build_score_explanation
from app.core.policy_engine import evaluate_policy, check_no_alternative_policy
from app.services.amadeus import search_alternative_flights
from app.services.websocket import broadcast
from app.agent.agent import run_recovery_agent


def _audit(db, trip_id, plan_id, action, inputs=None, outputs=None, result="SUCCESS", actor=AuditActor.SYSTEM):
    db.add(AuditLog(
        trip_id=trip_id,
        recovery_plan_id=plan_id,
        actor=actor,
        action=action,
        inputs=inputs,
        outputs=outputs,
        result=result,
    ))
    db.commit()


def _notify(db, trip_id, user_id, message, subject="Trip Update"):
    db.add(Notification(
        user_id=user_id,
        trip_id=trip_id,
        channel=NotificationChannel.IN_APP,
        subject=subject,
        message=message,
        status="SENT",
        sent_at=datetime.utcnow(),
    ))
    db.commit()


def start_recovery(trip_id: int, disruption_id: int):
    """Entry point — called as a FastAPI background task."""
    db = SessionLocal()
    try:
        _run_recovery_pipeline(db, trip_id, disruption_id)
    finally:
        db.close()


def _run_recovery_pipeline(db: Session, trip_id: int, disruption_id: int):
    import time
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    disruption = db.query(DisruptionEvent).filter(DisruptionEvent.id == disruption_id).first()
    if not trip or not disruption:
        return

    user_id = trip.user_id

    # ── Step 1: Mark trip as DISRUPTED ───────────────────────────
    trip.status = TripStatus.DISRUPTED
    db.commit()
    broadcast(trip_id, {"event": "TRIP_STATUS", "status": "DISRUPTED"})
    time.sleep(1.5)

    # ── Step 2: Create recovery plan ─────────────────────────────
    plan = RecoveryPlan(
        trip_id=trip_id,
        disruption_event_id=disruption_id,
        status=RecoveryPlanStatus.ANALYZING,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    broadcast(trip_id, {"event": "RECOVERY_STARTED", "plan_id": plan.id})
    time.sleep(2)

    # ── Step 3: Impact analysis ───────────────────────────────────
    impact = analyze_trip_impact(trip)
    _audit(db, trip_id, plan.id, "IMPACT_ANALYZED", outputs=impact)
    broadcast(trip_id, {"event": "IMPACT_ANALYZED", "impact": impact})
    time.sleep(1.5)

    if not impact["recovery_needed"]:
        plan.status = RecoveryPlanStatus.COMPLETED
        plan.reasoning = "No recovery needed — all connections remain viable."
        trip.status = TripStatus.HEALTHY
        db.commit()
        return

    # ── Step 4: Search alternatives ───────────────────────────────
    plan.status = RecoveryPlanStatus.PLAN_READY
    db.commit()
    broadcast(trip_id, {"event": "SEARCHING_ALTERNATIVES"})
    time.sleep(2)

    missed_segment = db.query(FlightSegment).filter(
        FlightSegment.trip_id == trip_id,
        FlightSegment.flight_number == impact.get("missed_flight")
    ).first()

    if not missed_segment:
        # fallback: use second segment
        segments = sorted(trip.flight_segments, key=lambda s: s.sequence_order)
        missed_segment = segments[1] if len(segments) > 1 else segments[0]

    # ── Step 5 (pre): Load user preferences before flight search ─────
    preferences = {"preferred_airlines": [], "preferred_cabin": None}
    if trip.user and trip.user.preferences:
        preferences = {
            "preferred_airlines": trip.user.preferences.preferred_airlines or [],
            "preferred_cabin": trip.user.preferences.preferred_cabin,
        }

    search_cabin = (
        preferences.get("preferred_cabin")
        or missed_segment.cabin_class
        or "ECONOMY"
    )
    alternatives = search_alternative_flights(
        origin=missed_segment.origin_airport,
        destination=missed_segment.destination_airport,
        date=missed_segment.scheduled_departure.date(),
        cabin=search_cabin,
        original_price_usd=missed_segment.price_usd or 0.0,
    )

    if not alternatives:
        policy_result = check_no_alternative_policy()
        plan.status = RecoveryPlanStatus.FAILED
        plan.policy_decision = PolicyDecision.ESCALATE
        plan.reasoning = policy_result["reason"]
        trip.status = TripStatus.ESCALATED
        db.commit()
        _notify(db, trip_id, user_id, "No alternative flights found. A support agent will contact you.", "Escalation Required")
        broadcast(trip_id, {"event": "ESCALATED", "reason": policy_result["reason"]})
        return

    policy_dict = {"auto_spend_limit": 150, "approval_spend_limit": 500, "max_spend_limit": 1000}
    if trip.user and trip.user.policy:
        p = trip.user.policy
        policy_dict = {
            "auto_spend_limit": p.auto_spend_limit,
            "approval_spend_limit": p.approval_spend_limit,
            "max_spend_limit": p.max_spend_limit,
            "allowed_cabins": p.allowed_cabins,
            "prohibited_airports": p.prohibited_airports,
            "require_same_airline": p.require_same_airline,
        }

    original_arrival = missed_segment.scheduled_arrival
    ranked = rank_alternatives(alternatives, original_arrival, preferences, policy_dict)
    best = ranked[0]
    explanation = build_score_explanation(best)

    broadcast(trip_id, {"event": "ALTERNATIVES_SCORED", "count": len(ranked), "best": best})
    time.sleep(2)

    # ── Step 6: Policy check ──────────────────────────────────────
    plan.status = RecoveryPlanStatus.POLICY_CHECK
    db.commit()
    broadcast(trip_id, {"event": "POLICY_CHECK"})
    time.sleep(1.5)

    extra_cost = best.get("extra_cost_usd", 0)
    policy_result = evaluate_policy(extra_cost, best, policy_dict)
    decision = policy_result["decision"]

    # ── Step 7: AI reasoning ──────────────────────────────────────
    ai_reasoning = run_recovery_agent(trip, impact, best, policy_result)

    plan.selected_flight = ranked          # store all ranked alternatives for frontend
    plan.total_extra_cost = extra_cost
    plan.policy_decision = decision
    plan.reasoning = f"{explanation}\n\n{ai_reasoning}"
    db.commit()

    _audit(db, trip_id, plan.id, "POLICY_EVALUATED",
           inputs={"extra_cost": extra_cost}, outputs=policy_result, actor=AuditActor.SYSTEM)

    if decision == PolicyDecision.AUTO:
        plan.status = RecoveryPlanStatus.EXECUTING
        db.commit()
        broadcast(trip_id, {"event": "AUTO_EXECUTING", "decision": "AUTO"})
        _execute_plan(db, plan, trip, best, impact)

    elif decision == PolicyDecision.APPROVAL:
        plan.status = RecoveryPlanStatus.AWAITING_APPROVAL
        trip.status = TripStatus.AT_RISK
        db.commit()
        _notify(db, trip_id, user_id,
                f"Recovery plan ready. Extra cost: ${extra_cost:.2f}. Your approval is needed.",
                "Approval Required")
        broadcast(trip_id, {"event": "AWAITING_APPROVAL", "plan_id": plan.id, "extra_cost": extra_cost})

    else:  # ESCALATE
        plan.status = RecoveryPlanStatus.FAILED
        trip.status = TripStatus.ESCALATED
        db.commit()
        _notify(db, trip_id, user_id,
                f"Recovery escalated to support. Reason: {policy_result['reason']}",
                "Escalated to Support")
        broadcast(trip_id, {"event": "ESCALATED", "reason": policy_result["reason"]})


def _execute_plan(db: Session, plan: RecoveryPlan, trip: Trip, best_flight: dict, impact: dict):
    import hashlib, json

    results = []

    def make_key(action_type, data):
        return hashlib.sha256(f"{plan.id}:{action_type}:{json.dumps(data, sort_keys=True)}".encode()).hexdigest()

    # Action 1: Rebook flight
    flight_key = make_key("REBOOK_FLIGHT", {"flight": best_flight.get("flight_number")})
    existing = db.query(RecoveryAction).filter(RecoveryAction.idempotency_key == flight_key).first()
    if not existing:
        action = RecoveryAction(
            recovery_plan_id=plan.id,
            action_type=ActionType.REBOOK_FLIGHT,
            status=ActionStatus.IN_PROGRESS,
            idempotency_key=flight_key,
            details=best_flight,
        )
        db.add(action)
        db.commit()
        broadcast(trip.id, {"event": "ACTION_STARTED", "type": "REBOOK_FLIGHT"})

        # Simulated execution — in production this calls airline API
        action.status = ActionStatus.COMPLETED
        action.result = {"booking_reference": f"RR-{plan.id}-NEW", "confirmed": True}
        action.executed_at = datetime.utcnow()
        db.commit()
        broadcast(trip.id, {"event": "ACTION_COMPLETED", "type": "REBOOK_FLIGHT"})
        results.append(("REBOOK_FLIGHT", "COMPLETED"))

        # Update the itinerary segment so it reflects the new flight
        seg = db.query(FlightSegment).filter(
            FlightSegment.trip_id == trip.id,
            FlightSegment.origin_airport == best_flight.get("origin"),
            FlightSegment.destination_airport == best_flight.get("destination"),
        ).first()
        if seg:
            seg.flight_number = best_flight.get("flight_number", seg.flight_number)
            seg.airline = best_flight.get("airline", seg.airline)
            seg.booking_reference = f"RR-{plan.id}-NEW"
            seg.delay_minutes = 0
            seg.status = FlightStatus.SCHEDULED
            if best_flight.get("departure_datetime"):
                try:
                    seg.estimated_departure = datetime.fromisoformat(best_flight["departure_datetime"])
                except ValueError:
                    pass
            if best_flight.get("arrival_datetime"):
                try:
                    seg.estimated_arrival = datetime.fromisoformat(best_flight["arrival_datetime"])
                except ValueError:
                    pass
            db.commit()

    # Action 2: Notify hotel whenever a flight was rebooked — itinerary changes always affect check-in
    from app.models import HotelBooking, HotelNotificationStatus
    from app.services.hotel_notify import notify_hotel_of_delay
    pending_hotels = (
        db.query(HotelBooking)
        .filter(
            HotelBooking.trip_id == trip.id,
            HotelBooking.notification_status != HotelNotificationStatus.NOTIFIED,
        )
        .all()
    )
    for hotel_booking in pending_hotels:
        hotel_key = make_key("MODIFY_HOTEL", {"hotel_id": hotel_booking.id})
        if db.query(RecoveryAction).filter(RecoveryAction.idempotency_key == hotel_key).first():
            continue

        new_eta = best_flight.get("arrival_datetime", "TBD")
        hotel_name  = hotel_booking.property_name
        hotel_email = hotel_booking.hotel_email or "reservations@hotel.demo"
        booking_ref = hotel_booking.booking_reference or "HTL-UNKNOWN"
        orig_checkin = hotel_booking.original_check_in_date or hotel_booking.check_in_date
        orig_checkin_str = orig_checkin.strftime("%Y-%m-%d %H:%M") if orig_checkin else "TBD"

        notify_result = notify_hotel_of_delay(
            hotel_name=hotel_name,
            hotel_email=hotel_email,
            booking_reference=booking_ref,
            original_checkin=orig_checkin_str,
            new_estimated_arrival=new_eta,
            delay_minutes=impact.get("delay_minutes", 0),
            guest_name=trip.user.name if trip.user else "Guest",
        )

        hotel_booking.notification_status = HotelNotificationStatus.NOTIFIED
        hotel_booking.notified_at = datetime.utcnow()
        hotel_booking.status = "UPDATED"
        if new_eta and new_eta != "TBD":
            try:
                hotel_booking.check_in_date = datetime.fromisoformat(new_eta)
            except (ValueError, TypeError):
                pass
        db.commit()

        hotel_action = RecoveryAction(
            recovery_plan_id=plan.id,
            action_type=ActionType.MODIFY_HOTEL,
            status=ActionStatus.COMPLETED,
            idempotency_key=hotel_key,
            details={"hotel_id": hotel_booking.id, "hotel_name": hotel_name},
            result=notify_result,
            executed_at=datetime.utcnow(),
        )
        db.add(hotel_action)
        db.commit()
        broadcast(trip.id, {"event": "ACTION_COMPLETED", "type": "MODIFY_HOTEL"})
        results.append(("MODIFY_HOTEL", "COMPLETED"))

    # Action 3: Reschedule transfer if needed
    transfer_impacts = [d for d in impact.get("downstream_impacts", []) if d["type"] == "TRANSFER" and d["status"] != "OK"]
    if transfer_impacts:
        transfer_key = make_key("RESCHEDULE_TRANSFER", {"transfer_impact": transfer_impacts[0]})
        existing_transfer = db.query(RecoveryAction).filter(RecoveryAction.idempotency_key == transfer_key).first()
        if not existing_transfer:
            transfer_action = RecoveryAction(
                recovery_plan_id=plan.id,
                action_type=ActionType.RESCHEDULE_TRANSFER,
                status=ActionStatus.COMPLETED,
                idempotency_key=transfer_key,
                details=transfer_impacts[0],
                result={"status": "Transfer rescheduled to match new arrival"},
                executed_at=datetime.utcnow(),
            )
            db.add(transfer_action)
            db.commit()
            broadcast(trip.id, {"event": "ACTION_COMPLETED", "type": "RESCHEDULE_TRANSFER"})
            results.append(("RESCHEDULE_TRANSFER", "COMPLETED"))

    # Action 4: Notify traveler
    notify_key = make_key("SEND_NOTIFICATION", {"plan": plan.id})
    existing_notif = db.query(RecoveryAction).filter(RecoveryAction.idempotency_key == notify_key).first()
    if not existing_notif:
        notify_action = RecoveryAction(
            recovery_plan_id=plan.id,
            action_type=ActionType.SEND_NOTIFICATION,
            status=ActionStatus.COMPLETED,
            idempotency_key=notify_key,
            details={"channel": "IN_APP"},
            result={"sent": True},
            executed_at=datetime.utcnow(),
        )
        db.add(notify_action)
        db.commit()

    # All done — mark plan and trip as recovered
    failed = [r for r in results if r[1] == "FAILED"]
    plan.status = RecoveryPlanStatus.PARTIALLY_COMPLETED if failed else RecoveryPlanStatus.COMPLETED
    trip.status = TripStatus.RECOVERED
    db.commit()

    _notify(db, trip.id, trip.user_id,
            f"Your trip has been recovered. New flight: {best_flight.get('flight_number')}. Extra cost: ${plan.total_extra_cost:.2f}.",
            "Trip Recovered ✓")
    broadcast(trip.id, {
        "event": "TRIP_RECOVERED",
        "plan_id": plan.id,
        "new_flight": best_flight.get("flight_number"),
        "extra_cost": plan.total_extra_cost,
        "reasoning": plan.reasoning,
    })


def execute_recovery_plan(plan_id: int):
    """Called when user approves an AWAITING_APPROVAL plan."""
    db = SessionLocal()
    try:
        plan = db.query(RecoveryPlan).filter(RecoveryPlan.id == plan_id).first()
        if not plan:
            return
        trip = db.query(Trip).filter(Trip.id == plan.trip_id).first()
        disruption = db.query(DisruptionEvent).filter(DisruptionEvent.id == plan.disruption_event_id).first()

        impact = analyze_trip_impact(trip)
        best_flight = plan.selected_flight[0] if isinstance(plan.selected_flight, list) else plan.selected_flight

        plan.status = RecoveryPlanStatus.EXECUTING
        db.commit()
        broadcast(plan.trip_id, {"event": "APPROVAL_EXECUTING"})
        _execute_plan(db, plan, trip, best_flight, impact)
    finally:
        db.close()
