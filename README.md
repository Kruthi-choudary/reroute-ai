# ReRoute AI — Travel Disruption Concierge

When a flight gets disrupted, this recovers the trip on its own: scores the impact on your connections and hotel, decides what it's allowed to do under your spend policy, rebooks the flight, adjusts the hotel, and tells you what happened — live, over a WebSocket. A human only gets pulled in when the policy says the cost warrants it.

**Live:** https://reroute-ai.onrender.com (API only — https://re-route-sandy.vercel.app is the actual app)

This repo is the backend. Frontend: [`ReRoute-ai_frontend`](https://github.com/Kruthi-choudary/ReRoute/).

## How it works

```
Background monitor polls active trips
        -> disruption detected
        -> impact scored (app/core/impact.py, scoring.py)
        -> policy engine decides: AUTO / AWAITING_APPROVAL / ESCALATE
        -> recovery orchestrator runs: rebook flight -> modify hotel -> notify traveller
        -> AI agent (Groq) explains the decision in plain language
        -> WebSocket pushes live status to the frontend
```

The policy engine is deterministic, not the LLM — `policy_engine.py` decides whether a rebooking auto-executes, needs approval, or escalates, purely off cost thresholds and rules. Groq (`llama-3.1-8b-instant`) only explains that decision in plain language after the fact; it never makes it. If `GROQ_API_KEY` is unset, the agent falls back to a deterministic explanation instead of silently failing.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, Alembic (migrations run automatically on startup, including a from-scratch path for a brand-new database)
- **Auth:** JWT (python-jose) + bcrypt, 7-day token TTL
- **Realtime:** WebSockets (`/ws/{trip_id}`), JWT-authenticated
- **AI:** Groq (OpenAI-compatible client) for recovery explanations
- **Flight data:** simulated by default; AirLabs API optional (`FLIGHT_DATA_PROVIDER=airlabs`)
- **DB:** SQLite for local dev; Postgres-ready via `DATABASE_URL`

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

All routes under `/api/*` require a JWT bearer token, except `/api/auth`, `/api/demo/*` (open, `DEMO_SECRET`-gated — for curl/local testing against any trip), and `/monitor` (ops visibility).

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

Every write endpoint derives its target from the JWT, not from client-supplied IDs — there's no path from one account to another account's trip, policy, or recovery plan.

Interactive docs at `http://localhost:8000/docs` (local) or `https://reroute-ai.onrender.com/docs` (live).
