from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON,
    ForeignKey, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()


# ── Enums ────────────────────────────────────────────────────────────────────

class TripStatus(str, enum.Enum):
    HEALTHY             = "HEALTHY"
    AT_RISK             = "AT_RISK"
    DISRUPTED           = "DISRUPTED"
    RECOVERING          = "RECOVERING"
    RECOVERED           = "RECOVERED"
    ESCALATED           = "ESCALATED"

class FlightStatus(str, enum.Enum):
    SCHEDULED           = "SCHEDULED"
    DELAYED             = "DELAYED"
    CANCELLED           = "CANCELLED"
    COMPLETED           = "COMPLETED"

class DisruptionType(str, enum.Enum):
    DELAY               = "DELAY"
    CANCELLATION        = "CANCELLATION"
    SCHEDULE_CHANGE     = "SCHEDULE_CHANGE"
    CONNECTION_AT_RISK  = "CONNECTION_AT_RISK"
    MISSED_CONNECTION   = "MISSED_CONNECTION"

class DisruptionSeverity(str, enum.Enum):
    LOW                 = "LOW"
    MEDIUM              = "MEDIUM"
    HIGH                = "HIGH"
    CRITICAL            = "CRITICAL"

class PolicyDecision(str, enum.Enum):
    AUTO                = "AUTO"
    APPROVAL            = "APPROVAL"
    ESCALATE            = "ESCALATE"

class RecoveryPlanStatus(str, enum.Enum):
    CREATED             = "CREATED"
    ANALYZING           = "ANALYZING"
    PLAN_READY          = "PLAN_READY"
    POLICY_CHECK        = "POLICY_CHECK"
    AWAITING_APPROVAL   = "AWAITING_APPROVAL"
    EXECUTING           = "EXECUTING"
    COMPLETED           = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED              = "FAILED"

class ActionType(str, enum.Enum):
    REBOOK_FLIGHT       = "REBOOK_FLIGHT"
    MODIFY_HOTEL        = "MODIFY_HOTEL"
    RESCHEDULE_TRANSFER = "RESCHEDULE_TRANSFER"
    SEND_NOTIFICATION   = "SEND_NOTIFICATION"

class ActionStatus(str, enum.Enum):
    PENDING             = "PENDING"
    IN_PROGRESS         = "IN_PROGRESS"
    COMPLETED           = "COMPLETED"
    FAILED              = "FAILED"
    SKIPPED             = "SKIPPED"

class NotificationChannel(str, enum.Enum):
    EMAIL               = "EMAIL"
    SMS                 = "SMS"
    PUSH                = "PUSH"
    IN_APP              = "IN_APP"

class AuditActor(str, enum.Enum):
    SYSTEM              = "SYSTEM"
    AI_AGENT            = "AI_AGENT"
    USER                = "USER"


# ── Tables ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String, unique=True, index=True, nullable=False)
    name          = Column(String, nullable=False)
    phone         = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)

    preferences = relationship("TravelerPreference", back_populates="user", uselist=False)
    policy      = relationship("PolicyRule", back_populates="user", uselist=False)
    trips       = relationship("Trip", back_populates="user")


class TravelerPreference(Base):
    __tablename__ = "traveler_preferences"

    id                 = Column(Integer, primary_key=True, index=True)
    user_id            = Column(Integer, ForeignKey("users.id"), unique=True)
    preferred_airlines = Column(JSON, default=list)   # ["EK", "BA"]
    preferred_cabin    = Column(String, default="ECONOMY")
    max_stops          = Column(Integer, default=1)
    seat_preference    = Column(String, default="WINDOW")
    updated_at         = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="preferences")


class PolicyRule(Base):
    __tablename__ = "policy_rules"

    id                   = Column(Integer, primary_key=True, index=True)
    user_id              = Column(Integer, ForeignKey("users.id"), unique=True)
    auto_spend_limit     = Column(Float, default=150.0)   # USD — auto rebook below this
    approval_spend_limit = Column(Float, default=500.0)   # USD — ask approval below this
    max_spend_limit      = Column(Float, default=1000.0)  # USD — escalate above this
    allowed_cabins       = Column(JSON, default=lambda: ["ECONOMY", "PREMIUM_ECONOMY"])
    prohibited_airports  = Column(JSON, default=list)
    require_same_airline = Column(Boolean, default=False)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="policy")


class Trip(Base):
    __tablename__ = "trips"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), index=True)
    name           = Column(String, nullable=False)           # "London Business Trip"
    origin         = Column(String, nullable=False)           # "HYD"
    destination    = Column(String, nullable=False)           # "LHR"
    departure_date = Column(DateTime, nullable=False)
    return_date    = Column(DateTime, nullable=True)
    status         = Column(SAEnum(TripStatus), default=TripStatus.HEALTHY, index=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    updated_at     = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user             = relationship("User", back_populates="trips")
    flight_segments  = relationship("FlightSegment", back_populates="trip", order_by="FlightSegment.sequence_order")
    hotel_bookings   = relationship("HotelBooking", back_populates="trip")
    transfers        = relationship("Transfer", back_populates="trip")
    disruption_events = relationship("DisruptionEvent", back_populates="trip")
    recovery_plans   = relationship("RecoveryPlan", back_populates="trip")
    audit_logs       = relationship("AuditLog", back_populates="trip")


class FlightSegment(Base):
    __tablename__ = "flight_segments"

    id                   = Column(Integer, primary_key=True, index=True)
    trip_id              = Column(Integer, ForeignKey("trips.id"), index=True)
    sequence_order       = Column(Integer, nullable=False)    # 1, 2, 3 ...
    flight_number        = Column(String, nullable=False)     # "EK527"
    airline              = Column(String, nullable=False)     # "EK"
    origin_airport       = Column(String, nullable=False)     # "HYD"
    destination_airport  = Column(String, nullable=False)     # "DXB"
    scheduled_departure  = Column(DateTime, nullable=False)
    scheduled_arrival    = Column(DateTime, nullable=False)
    estimated_departure  = Column(DateTime, nullable=True)
    estimated_arrival    = Column(DateTime, nullable=True)
    terminal_origin      = Column(String, nullable=True)
    terminal_destination = Column(String, nullable=True)
    cabin_class          = Column(String, default="ECONOMY")
    booking_reference    = Column(String, nullable=True)
    price_usd            = Column(Float, nullable=True, default=0.0)
    status               = Column(SAEnum(FlightStatus), default=FlightStatus.SCHEDULED)
    delay_minutes        = Column(Integer, default=0)

    trip = relationship("Trip", back_populates="flight_segments")


class HotelBooking(Base):
    __tablename__ = "hotel_bookings"

    id                = Column(Integer, primary_key=True, index=True)
    trip_id           = Column(Integer, ForeignKey("trips.id"), index=True)
    property_name     = Column(String, nullable=False)
    city              = Column(String, nullable=False)
    check_in_date     = Column(DateTime, nullable=False)
    check_out_date    = Column(DateTime, nullable=False)
    booking_reference = Column(String, nullable=True)
    earliest_check_in = Column(String, default="14:00")
    latest_check_in   = Column(String, default="23:59")
    status            = Column(String, default="CONFIRMED")

    trip = relationship("Trip", back_populates="hotel_bookings")


class Transfer(Base):
    __tablename__ = "transfers"

    id                = Column(Integer, primary_key=True, index=True)
    trip_id           = Column(Integer, ForeignKey("trips.id"), index=True)
    pickup_location   = Column(String, nullable=False)        # "LHR Terminal 5"
    pickup_time       = Column(DateTime, nullable=False)
    destination       = Column(String, nullable=False)        # "London City Hotel"
    booking_reference = Column(String, nullable=True)
    status            = Column(String, default="CONFIRMED")

    trip = relationship("Trip", back_populates="transfers")


class DisruptionEvent(Base):
    __tablename__ = "disruption_events"

    id                 = Column(Integer, primary_key=True, index=True)
    trip_id            = Column(Integer, ForeignKey("trips.id"), index=True)
    flight_segment_id  = Column(Integer, ForeignKey("flight_segments.id"), nullable=True, index=True)
    idempotency_key    = Column(String, unique=True, index=True)  # prevents duplicate processing
    disruption_type    = Column(SAEnum(DisruptionType), nullable=False)
    severity           = Column(SAEnum(DisruptionSeverity), default=DisruptionSeverity.MEDIUM)
    previous_state     = Column(JSON)   # snapshot before disruption
    new_state          = Column(JSON)   # snapshot after disruption
    description        = Column(Text, nullable=True)
    detected_at        = Column(DateTime, default=datetime.utcnow)
    processed          = Column(Boolean, default=False)

    trip           = relationship("Trip", back_populates="disruption_events")
    flight_segment = relationship("FlightSegment")
    recovery_plans = relationship("RecoveryPlan", back_populates="disruption_event")


class RecoveryPlan(Base):
    __tablename__ = "recovery_plans"

    id                  = Column(Integer, primary_key=True, index=True)
    trip_id             = Column(Integer, ForeignKey("trips.id"), index=True)
    disruption_event_id = Column(Integer, ForeignKey("disruption_events.id"), index=True)
    strategy            = Column(Text, nullable=True)         # human-readable plan summary
    total_extra_cost    = Column(Float, default=0.0)
    reasoning           = Column(Text, nullable=True)         # AI + scoring explanation
    policy_decision     = Column(SAEnum(PolicyDecision), nullable=True)
    status              = Column(SAEnum(RecoveryPlanStatus), default=RecoveryPlanStatus.CREATED)
    selected_flight     = Column(JSON, nullable=True)         # chosen alternative flight data
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trip             = relationship("Trip", back_populates="recovery_plans")
    disruption_event = relationship("DisruptionEvent", back_populates="recovery_plans")
    actions          = relationship("RecoveryAction", back_populates="recovery_plan")
    audit_logs       = relationship("AuditLog", back_populates="recovery_plan")


class RecoveryAction(Base):
    __tablename__ = "recovery_actions"

    id               = Column(Integer, primary_key=True, index=True)
    recovery_plan_id = Column(Integer, ForeignKey("recovery_plans.id"), index=True)
    action_type      = Column(SAEnum(ActionType), nullable=False)
    status           = Column(SAEnum(ActionStatus), default=ActionStatus.PENDING)
    idempotency_key  = Column(String, unique=True, index=True)
    details          = Column(JSON, default=dict)   # action-specific payload
    result           = Column(JSON, nullable=True)  # execution result
    error_message    = Column(Text, nullable=True)
    executed_at      = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    recovery_plan = relationship("RecoveryPlan", back_populates="actions")


class Notification(Base):
    __tablename__ = "notifications"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), index=True)
    trip_id    = Column(Integer, ForeignKey("trips.id"), nullable=True, index=True)
    channel    = Column(SAEnum(NotificationChannel), default=NotificationChannel.IN_APP)
    subject    = Column(String, nullable=True)
    message    = Column(Text, nullable=False)
    status     = Column(String, default="PENDING")
    sent_at    = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id               = Column(Integer, primary_key=True, index=True)
    trip_id          = Column(Integer, ForeignKey("trips.id"), nullable=True, index=True)
    recovery_plan_id = Column(Integer, ForeignKey("recovery_plans.id"), nullable=True, index=True)
    actor            = Column(SAEnum(AuditActor), default=AuditActor.SYSTEM)
    action           = Column(String, nullable=False)   # "DISRUPTION_DETECTED", "PLAN_CREATED" etc.
    inputs           = Column(JSON, nullable=True)
    outputs          = Column(JSON, nullable=True)
    result           = Column(String, nullable=True)    # "SUCCESS" / "FAILURE"
    created_at       = Column(DateTime, default=datetime.utcnow)

    trip          = relationship("Trip", back_populates="audit_logs")
    recovery_plan = relationship("RecoveryPlan", back_populates="audit_logs")
