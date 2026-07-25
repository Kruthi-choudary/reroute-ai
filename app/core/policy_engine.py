"""
Policy Engine — deterministic authorization boundary.
The AI proposes; policy decides.
"""
from typing import Dict, Any, Optional
from app.models import PolicyDecision


def evaluate_policy(
    extra_cost_usd: float,
    selected_flight: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Returns a PolicyDecision and the reason for it.
    This is purely deterministic — no LLM involved.
    """
    auto_limit     = policy.get("auto_spend_limit", 150.0)
    approval_limit = policy.get("approval_spend_limit", 500.0)
    max_limit      = policy.get("max_spend_limit", 1000.0)
    allowed_cabins = policy.get("allowed_cabins", ["ECONOMY", "PREMIUM_ECONOMY"])
    prohibited_airports = policy.get("prohibited_airports", [])
    require_same_airline = policy.get("require_same_airline", False)

    reasons = []

    # Hard blocks — these force ESCALATE regardless of cost
    flight_cabin = selected_flight.get("cabin_class", "ECONOMY")
    if flight_cabin not in allowed_cabins:
        return {
            "decision": PolicyDecision.ESCALATE,
            "reason": f"Cabin class {flight_cabin} not in allowed cabins {allowed_cabins}",
            "extra_cost_usd": extra_cost_usd,
        }

    via_airport = selected_flight.get("via_airport")
    if via_airport and via_airport in prohibited_airports:
        return {
            "decision": PolicyDecision.ESCALATE,
            "reason": f"Route goes via prohibited airport {via_airport}",
            "extra_cost_usd": extra_cost_usd,
        }

    if require_same_airline:
        original_airline = policy.get("original_airline")
        new_airline = selected_flight.get("airline")
        if original_airline and new_airline != original_airline:
            reasons.append(f"Airline changed from {original_airline} to {new_airline} — requires approval")
            return {
                "decision": PolicyDecision.APPROVAL,
                "reason": "; ".join(reasons),
                "extra_cost_usd": extra_cost_usd,
            }

    # Cost-based decision
    if extra_cost_usd <= auto_limit:
        return {
            "decision": PolicyDecision.AUTO,
            "reason": f"Extra cost ${extra_cost_usd:.2f} is within auto-rebook limit ${auto_limit:.2f}",
            "extra_cost_usd": extra_cost_usd,
        }
    elif extra_cost_usd <= approval_limit:
        return {
            "decision": PolicyDecision.APPROVAL,
            "reason": f"Extra cost ${extra_cost_usd:.2f} exceeds auto limit ${auto_limit:.2f} — approval required",
            "extra_cost_usd": extra_cost_usd,
        }
    else:
        return {
            "decision": PolicyDecision.ESCALATE,
            "reason": f"Extra cost ${extra_cost_usd:.2f} exceeds maximum allowed ${max_limit:.2f} — escalating to support",
            "extra_cost_usd": extra_cost_usd,
        }


def check_no_alternative_policy() -> Dict[str, Any]:
    """Called when no viable alternative exists."""
    return {
        "decision": PolicyDecision.ESCALATE,
        "reason": "No policy-compliant alternative found — human intervention required",
        "extra_cost_usd": 0,
    }
