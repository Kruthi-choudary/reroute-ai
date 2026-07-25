"""
Alternative Flight Scoring Engine — deterministic, auditable.
LLM explains the result; this code makes the decision.
"""
from datetime import datetime
from typing import List, Dict, Any


WEIGHTS = {
    "arrival_time":    0.35,
    "cost":            0.25,
    "convenience":     0.15,
    "reliability":     0.15,
    "preference":      0.10,
}


def score_alternative(
    flight: Dict[str, Any],
    original_arrival: datetime,
    preferences: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Scores a single alternative flight candidate.
    Returns the flight dict enriched with score breakdown.
    """
    scores = {}

    # 1. Arrival time — prefer earlier (normalize against a 12h window)
    flight_arrival = flight.get("arrival_datetime")
    if isinstance(flight_arrival, str):
        flight_arrival = datetime.fromisoformat(flight_arrival)

    if flight_arrival:
        hours_late = max(0, (flight_arrival - original_arrival).total_seconds() / 3600)
        scores["arrival_time"] = max(0.0, 1.0 - (hours_late / 12))
    else:
        scores["arrival_time"] = 0.0

    # 2. Cost — lower extra cost scores higher
    extra_cost = flight.get("extra_cost_usd", 0)
    max_cost = policy.get("max_spend_limit", 1000)
    scores["cost"] = max(0.0, 1.0 - (extra_cost / max_cost))

    # 3. Convenience — fewer stops is better
    stops = flight.get("stops", 0)
    scores["convenience"] = 1.0 if stops == 0 else (0.6 if stops == 1 else 0.2)

    # 4. Reliability — use on-time percentage if available
    on_time_pct = flight.get("on_time_percentage", 75)
    scores["reliability"] = on_time_pct / 100

    # 5. Preference — preferred airline match
    preferred_airlines = preferences.get("preferred_airlines", [])
    airline = flight.get("airline", "")
    scores["preference"] = 1.0 if airline in preferred_airlines else 0.3

    # Weighted total
    total = sum(WEIGHTS[k] * scores[k] for k in WEIGHTS)

    return {
        **flight,
        "score_breakdown": scores,
        "total_score": round(total, 4),
        "weights_used": WEIGHTS,
    }


def rank_alternatives(
    flights: List[Dict[str, Any]],
    original_arrival: datetime,
    preferences: Dict[str, Any],
    policy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Scores and ranks all alternatives, best first."""
    scored = [
        score_alternative(f, original_arrival, preferences, policy)
        for f in flights
    ]
    return sorted(scored, key=lambda x: x["total_score"], reverse=True)


def build_score_explanation(flight: Dict[str, Any]) -> str:
    """
    Builds a human-readable explanation from the score breakdown.
    Used by the AI agent to explain WHY this option was chosen.
    """
    bd = flight.get("score_breakdown", {})
    lines = []

    if bd.get("arrival_time", 0) > 0.7:
        lines.append("arrives significantly earlier than other options")
    if bd.get("cost", 0) > 0.8:
        lines.append("minimal additional cost")
    if bd.get("convenience", 0) == 1.0:
        lines.append("direct flight with no additional connections")
    elif bd.get("convenience", 0) > 0.5:
        lines.append("only one additional stop")
    if bd.get("reliability", 0) > 0.8:
        lines.append("high on-time reliability")
    if bd.get("preference", 0) == 1.0:
        lines.append("matches preferred airline")

    if not lines:
        lines.append("best available option given policy constraints")

    return "Selected because: " + ", ".join(lines) + "."
