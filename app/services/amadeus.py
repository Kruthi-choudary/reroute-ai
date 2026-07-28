"""
AirLabs flight search service.
Free plan: 1,000 req/month, HTTPS included.
Get key at: airlabs.co
"""
import os
import httpx
from datetime import date, datetime
from typing import List, Dict, Any

AIRLABS_API_KEY = os.getenv("AIRLABS_API_KEY", "")

_BASE_URL = "https://airlabs.co/api/v9"

_PRICE_MULTIPLIERS = [1.25, 1.10, 0.95, 1.35, 1.05]


def search_alternative_flights(
    origin: str,
    destination: str,
    date: date,
    cabin: str = "ECONOMY",
    original_price_usd: float = 0.0,
) -> List[Dict[str, Any]]:
    if not AIRLABS_API_KEY:
        return _mock_alternatives(origin, destination, date, original_price_usd)

    try:
        # Try schedules first (better for future dates)
        resp = httpx.get(
            f"{_BASE_URL}/schedules",
            params={
                "api_key":  AIRLABS_API_KEY,
                "dep_iata": origin,
                "arr_iata": destination,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        results = _parse_response(resp.json(), origin, destination, date, original_price_usd)
        if results:
            return results

        # Fall back to live flights
        print("[AirLabs] No schedules found — trying live flights")
        return _fetch_live(origin, destination, date, original_price_usd)
    except Exception as e:
        print(f"[AirLabs] API error: {e} — using mock data")
        return _mock_alternatives(origin, destination, date, original_price_usd)


def _fetch_live(origin: str, destination: str, flight_date: date, original_price_usd: float) -> List[Dict[str, Any]]:
    try:
        resp = httpx.get(
            f"{_BASE_URL}/flights",
            params={
                "api_key":  AIRLABS_API_KEY,
                "dep_iata": origin,
                "arr_iata": destination,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        results = _parse_response(resp.json(), origin, destination, flight_date, original_price_usd)
        return results if results else _mock_alternatives(origin, destination, flight_date, original_price_usd)
    except Exception as e:
        print(f"[AirLabs] Live fallback error: {e} — using mock data")
        return _mock_alternatives(origin, destination, flight_date, original_price_usd)


def _parse_response(
    data: dict,
    origin: str,
    destination: str,
    flight_date: date,
    original_price_usd: float,
) -> List[Dict[str, Any]]:
    results = []
    for i, flight in enumerate(data.get("response", [])):
        try:
            # AirLabs uses flat fields: dep_time/arr_time or dep_time_utc/arr_time_utc
            dep_time = flight.get("dep_time_utc") or flight.get("dep_time")
            arr_time = flight.get("arr_time_utc") or flight.get("arr_time")
            if not dep_time or not arr_time:
                continue

            dep_time = _rebase_to_date(dep_time, flight_date)
            arr_time = _rebase_to_date(arr_time, flight_date)

            base  = original_price_usd if original_price_usd > 0 else 300.0
            price = round(base * _PRICE_MULTIPLIERS[i % len(_PRICE_MULTIPLIERS)], 2)

            results.append({
                "flight_number":      flight.get("flight_iata") or flight.get("flight_icao", f"F{i}"),
                "airline":            flight.get("airline_iata") or flight.get("airline_icao", ""),
                "origin":             flight.get("dep_iata", origin),
                "destination":        flight.get("arr_iata", destination),
                "departure_datetime": dep_time,
                "arrival_datetime":   arr_time,
                "stops":              0,
                "cabin_class":        "ECONOMY",
                "total_price_usd":    price,
                "extra_cost_usd":     max(0.0, price - original_price_usd),
                "on_time_percentage": 80,
                "source":             "airlabs",
            })
        except (KeyError, ValueError, TypeError):
            continue
    return results[:5]


def _rebase_to_date(time_str: str, target: date) -> str:
    """Shift a flight's time to the target date, preserving HH:MM."""
    try:
        # AirLabs returns "YYYY-MM-DD HH:MM" or ISO format
        dt = datetime.fromisoformat(time_str.replace(" ", "T").replace("Z", "+00:00"))
        rebased = dt.replace(year=target.year, month=target.month, day=target.day)
        return rebased.isoformat()
    except ValueError:
        return time_str


def _mock_alternatives(
    origin: str,
    destination: str,
    flight_date: date,
    original_price_usd: float = 0.0,
) -> List[Dict[str, Any]]:
    base = datetime.combine(flight_date, datetime.min.time())
    mock_fares = [
        ("XX001", "XX", 14, 0,  18, 30, 420.0, 88, 0),
        ("YY202", "YY", 13, 30, 18,  0, 380.0, 82, 0),
        ("ZZ310", "ZZ", 16,  0, 22, 45, 290.0, 75, 1),
    ]
    results = []
    for flight_number, airline, dep_h, dep_m, arr_h, arr_m, price, otp, stops in mock_fares:
        results.append({
            "flight_number":      flight_number,
            "airline":            airline,
            "origin":             origin,
            "destination":        destination,
            "departure_datetime": base.replace(hour=dep_h, minute=dep_m).isoformat(),
            "arrival_datetime":   base.replace(hour=arr_h, minute=arr_m).isoformat(),
            "stops":              stops,
            "cabin_class":        "ECONOMY",
            "total_price_usd":    price,
            "extra_cost_usd":     max(0.0, price - original_price_usd),
            "on_time_percentage": otp,
            "source":             "mock",
        })
    return results
