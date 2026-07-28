"""
AI Recovery Agent — reasoning and explanation layer.
Coordinates tools, interprets context, generates explanations.
Authorization and execution remain in deterministic backend code.
"""
import os
from typing import Dict, Any

SYSTEM_PROMPT = """You are ReRoute AI, an intelligent travel recovery agent.
Your job is to reason about travel disruptions and explain recovery decisions clearly.

You do NOT make authorization decisions — those are handled by the policy engine.
You do NOT execute bookings — the execution engine handles that.
Your role: reason about the situation, explain the chosen recovery, and provide context.

Always be concise and factual. Base explanations on the actual score and policy data provided.
Never invent information not present in the context."""


def run_recovery_agent(
    trip: Any,
    impact: Dict[str, Any],
    best_flight: Dict[str, Any],
    policy_result: Dict[str, Any],
) -> str:
    """
    Generates a natural language explanation of the recovery decision.
    Returns a string — purely informational, not authoritative.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return _fallback_explanation(trip, impact, best_flight, policy_result)

    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    prompt = f"""
Trip: {trip.name} ({trip.origin} → {trip.destination})
Disruption: {impact.get('delay_minutes')} minute delay on first flight
Missed connection: {impact.get('missed_flight')}
Connection broken at: {impact.get('broken_at')}

Best alternative found:
- Flight: {best_flight.get('flight_number')} ({best_flight.get('airline')})
- Departure: {best_flight.get('departure_datetime')}
- Arrival: {best_flight.get('arrival_datetime')}
- Stops: {best_flight.get('stops')}
- Extra cost: ${best_flight.get('extra_cost_usd', 0):.2f}
- Score: {best_flight.get('total_score', 0):.3f}
- Score breakdown: {best_flight.get('score_breakdown', {})}

Policy decision: {policy_result.get('decision')}
Policy reason: {policy_result.get('reason')}

Downstream impacts: {impact.get('downstream_impacts', [])}

Write a 2-3 sentence explanation of why this recovery option was selected and what happens next.
Be specific about the flights and timing. Do not repeat the policy reason verbatim.
"""

    try:
        response = client.chat.completions.create(
            model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Agent] Groq error: {e} — using fallback explanation")
        return _fallback_explanation(trip, impact, best_flight, policy_result)


def _fallback_explanation(trip, impact, best_flight, policy_result) -> str:
    """Deterministic fallback when OpenAI is unavailable."""
    flight_num  = best_flight.get("flight_number", "alternative flight")
    stops       = best_flight.get("stops", 0)
    extra_cost  = best_flight.get("extra_cost_usd", 0)
    delay       = impact.get("delay_minutes", 0)
    decision    = policy_result.get("decision", "AUTO")

    stop_text = "direct" if stops == 0 else f"{stops}-stop"
    cost_text = f"${extra_cost:.2f} additional cost" if extra_cost > 0 else "no additional cost"

    return (
        f"The {delay}-minute delay on your first flight made the connection impossible. "
        f"{flight_num} was selected as the best {stop_text} alternative with {cost_text}. "
        f"Decision: {decision} — {policy_result.get('reason', '')}."
    )
