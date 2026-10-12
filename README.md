# ReRoute AI — Travel Disruption Concierge

**Live:** https://reroute-ai.onrender.com-(API only ) https://re-route-sandy.vercel.app is the actual app

## The problem

When a flight gets delayed or cancelled, recovering the rest of the trip is manual and slow: you have to notice the disruption yourself, figure out whether your connection is even still makeable, search for an alternative flight, work out if the new cost is worth it, call the airline, then separately deal with the hotel and the airport transfer that no longer line up with your new arrival time. Airlines handle the flight; nothing handles the rest of the trip.

## What this does

ReRoute AI watches a trip end-to-end and recovers it automatically when something breaks:

1. **Detects the disruption** — a delay or cancellation comes in on a flight segment
2. **Scores the impact** — walks the itinerary as a dependency graph: is the next connection still makeable? Does the hotel check-in window still work? Is the airport transfer still timed correctly?
3. **Searches alternatives** — finds replacement flights and scores each one on price, duration, reliability, and the traveller's own preferences
4. **Decides under a policy, not a vibe** — a deterministic policy engine decides whether the best alternative auto-executes, needs the traveller's explicit approval, or has to escalate to a human, purely based on cost thresholds and rules the traveller set themselves
5. **Executes the recovery** — rebooks the flight, updates the hotel reservation, reschedules the transfer, and notifies the traveller
6. **Explains itself** — an LLM (Groq) writes a plain-language explanation of what happened and why, after the fact

Every step pushes live over a WebSocket, so the frontend shows the pipeline running in real time rather than a spinner with no information.

## Why the AI doesn't make the decision

The tempting design is "let the LLM decide what to rebook." This doesn't do that, on purpose. `policy_engine.py` is pure deterministic logic — cost thresholds, cabin-class rules, airline-change rules — with zero LLM involvement. The LLM's only job is to explain a decision that's already been made by that deterministic code, in `agent/agent.py`. If `GROQ_API_KEY` is missing, the agent falls back to a templated explanation instead of breaking — the recovery still happens either way.

This matters because a travel-recovery system that auto-spends money needs an authorization boundary a human can audit and trust, not a model that might hallucinate a $2,000 business-class rebooking. The policy engine is the boundary; the AI is just the explainer standing next to it.

## The policy / approval flow

Each traveller has a `PolicyRule`: an auto-approve spend limit, a hard escalation ceiling, allowed cabin classes, and optional airline/airport restrictions. When a disruption hits:
- Extra cost under the auto-limit → rebooked immediately, no human involved
- Extra cost between the auto-limit and the escalation ceiling → held as `AWAITING_APPROVAL`, traveller reviews the AI's reasoning and the candidate flights, then approves or rejects
- Extra cost over the ceiling, or no viable alternative exists → escalated to a human agent

This is the actual interesting part of the system: it's not "AI books whatever," it's AI-assisted decision-making with a deterministic, user-controlled authorization layer in front of it.

## Architecture

```
Background monitor polls active trips
        -> disruption detected
        -> impact scored (app/core/impact.py, scoring.py)
        -> policy engine decides: AUTO / AWAITING_APPROVAL / ESCALATE
        -> recovery orchestrator runs: rebook flight -> modify hotel -> notify traveller
        -> AI agent (Groq) explains the decision in plain language
        -> WebSocket pushes live status to the frontend
```

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, Alembic (migrations run automatically on startup, including a from-scratch path for a brand-new database — not just incremental deltas assuming a pre-existing schema)
- **Auth:** JWT (python-jose) + bcrypt, 7-day token TTL
- **Realtime:** WebSockets (`/ws/{trip_id}`), JWT-authenticated
- **AI:** Groq (OpenAI-compatible client) for recovery explanations
- **Flight data:** simulated by default; AirLabs API optional (`FLIGHT_DATA_PROVIDER=airlabs`)
- **DB:** SQLite for local dev; Postgres-ready via `DATABASE_URL`

## Security

Every write endpoint derives its target (which trip, which policy, which recovery plan) from the authenticated JWT, never from a client-supplied ID — there's no path from one account to reading or mutating another account's data. `JWT_SECRET` has no insecure fallback; the app refuses to start without one set. The open `/api/demo/*` endpoints (for curl/local testing against any trip) are gated behind `DEMO_SECRET` and loudly warn at startup if that's unset — separate from `/api/demo/self/*`, which is JWT-scoped to the caller's own trip and safe to expose publicly.

## Try the live demo

The fastest way to see the whole pipeline run: go to https://re-route-sandy.vercel.app, sign up with any email, open **Recovery Center**, and click **Simulate disruption**. That seeds a real trip and injects a 165-minute delay into the real pipeline described above — nothing from that point on is mocked. It'll land on **Awaiting approval** (the replacement flight costs more than the default auto-approve limit), and clicking **Approve** actually executes the rebooking, hotel update, and notification.

## Project layout

```
app/
  api/        auth, users, trips, disruptions, recovery, policies, notifications, hotels, demo, monitor
  core/       auth, policy_engine, recovery_orchestrator, impact/scoring, logging
  agent/      AI recovery agent (Groq) — reasoning/explanation only
  services/   websocket broadcast, flight monitor polling, hotel notifications
  static/     demo UI, served at /ui
migrations/   Alembic
```

## Setup

```bash
cd reroute_ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in JWT_SECRET, GROQ_API_KEY, etc.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
```

Run the frontend separately (see its own README) and point it at `http://localhost:8000`.

## Environment variables

See `.env.example`. Key ones:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection string (omit for local SQLite) |
| `JWT_SECRET` | Signing secret for auth tokens — required, no insecure fallback |
| `GROQ_API_KEY` | Enables AI-generated recovery explanations (optional) |
| `FLIGHT_DATA_PROVIDER` | `simulated` (default) or `airlabs` |
| `DEMO_SECRET` | Protects `/api/demo/*` endpoints outside local dev |
| `CORS_ORIGINS` | Comma-separated frontend origins |

## API

All routes under `/api/*` require a JWT bearer token, except `/api/auth`, `/api/demo/*` (open, `DEMO_SECRET`-gated), and `/monitor` (ops visibility).

| Router | Prefix |
|---|---|
| Auth | `/api/auth` |
| Users | `/api/users` |
| Trips | `/api/trips` |
| Disruptions | `/api/disruptions` |
| Recovery | `/api/recovery` |
| Policies | `/api/policies` |
| Notifications | `/api/notifications` |
| Hotels | `/api/hotels` |
| Demo — open, curl-friendly (seed/reset/trigger any trip by id) | `/api/demo` |
| Demo — authenticated self-serve (powers the frontend's "Simulate disruption" button; always acts on the caller's own trip) | `/api/demo/self` |

Interactive docs at `http://localhost:8000/docs` (local) or `https://reroute-ai.onrender.com/docs` (live).

This repo is the backend. Frontend: [`ReRoute-ai_frontend`](https://github.com/Kruthi-choudary/ReRoute/).
