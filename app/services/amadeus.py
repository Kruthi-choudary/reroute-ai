"""
Amadeus flight search service.
Uses the Amadeus test/sandbox API in dev, real API in production.
Falls back to mock data if credentials are not set.
"""
import os
import httpx
from datetime import date, datetime, timedelta
from typing import List, Dict, Any

AMADEUS_CLIENT_ID     = os.getenv("AMADEUS_CLIENT_ID", "")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET", "")
AMADEUS_BASE_URL      = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")

_token_cache = {"token": None, "expires_at": None}


def _get_token() -> str:
    now = datetime.utcnow()
    if _token_cache["token"] and _token_cache["expires_at"] > now:
        return _token_cache["token"]

    resp = httpx.post(
        f"{AMADEUS_BASE_URL}/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": AMADEUS_CLIENT_ID,
            "client_secret": AMADEUS_CLIENT_SECRET,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + timedelta(seconds=data["expires_in"] - 60)
    return _token_cache["token"]


def search_alternative_flights(
    origin: str,
    destination: str,
    date: date,
    cabin: str = "ECONOMY",
    original_price_usd: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Search for alternative flights. Falls back to mock data if
    Amadeus credentials are not configured.
    """
    if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
        return _mock_alternatives(origin, destination, date, original_price_usd)

    try:
        token = _get_token()
        resp = httpx.get(
            f"{AMADEUS_BASE_URL}/v2/shopping/flight-offers",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "originLocationCode":      origin,
                "destinationLocationCode": destination,
                "departureDate":           date.isoformat(),
                "adults":                  1,
                "travelClass":             cabin,
                "max":                     5,
                "currencyCode":            "USD",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        return _parse_amadeus_response(resp.json(), original_price_usd=original_price_usd)
    except Exception as e:
        print(f"[Amadeus] API error: {e} — using mock data")
        return _mock_alternatives(origin, destination, date, original_price_usd)


def _parse_amadeus_response(data: dict, original_price_usd: float = 0.0) -> List[Dict[str, Any]]:
    results = []
    for offer in data.get("data", []):
        try:
            itinerary = offer["itineraries"][0]
            first_seg = itinerary["segments"][0]
            last_seg  = itinerary["segments"][-1]
            price     = float(offer["price"]["total"])

            results.append({
                "flight_number":    first_seg["carrierCode"] + first_seg["number"],
                "airline":          first_seg["carrierCode"],
                "origin":           first_seg["departure"]["iataCode"],
                "destination":      last_seg["arrival"]["iataCode"],
                "departure_datetime": first_seg["departure"]["at"],
                "arrival_datetime": last_seg["arrival"]["at"],
                "stops":            len(itinerary["segments"]) - 1,
                "cabin_class":      "ECONOMY",
                "total_price_usd":  price,
                "extra_cost_usd":   max(0, price - original_price_usd),
                "on_time_percentage": 80,
                "source":           "amadeus",
            })
        except (KeyError, IndexError):
            continue
    return results


def _mock_alternatives(origin: str, destination: str, flight_date: date, original_price_usd: float = 0.0) -> List[Dict[str, Any]]:
    """
    Deterministic mock flights for demo purposes.
    Same pipeline, same scoring, same policy check — only the data source is fake.
    """
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
