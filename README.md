# ReRoute AI — Travel Disruption Concierge

Full-stack app that automatically recovers a trip when a flight is disrupted: detects the disruption, scores its impact, decides a recovery action under a user-defined spend policy, rebooks the flight, adjusts hotel reservations, and notifies the traveller — live, over a WebSocket.

This repo is the backend. The frontend lives in a sibling repo: [`ReRoute-ai_frontend`](../ReRoute-ai_frontend).

> **Status:** local prototype, not deployed. Built as a group portfolio project.

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

The LLM (Groq `llama-3.1-8b-instant`) is explanation-only — it never decides or executes a recovery action. All authorization logic lives in `policy_engine.py`; all execution lives in `recovery_orchestrator.py`. If `GROQ_API_KEY` is unset, the agent falls back to a deterministic explanation.

## Tech stack

- **Backend:** FastAPI, SQLAlchemy, Alembic (migrations run automatically on startup)
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
| `JWT_SECRET` | Signing secret for auth tokens |
| `GROQ_API_KEY` | Enables AI-generated recovery explanations (optional) |
| `FLIGHT_DATA_PROVIDER` | `simulated` (default) or `airlabs` |
| `DEMO_SECRET` | Protects `/api/demo/*` endpoints outside local dev |
| `CORS_ORIGINS` | Comma-separated frontend origins |

## API

All routes under `/api/*` except `/api/demo/*` (open, for seeding/resetting demo data) and `/monitor` (ops visibility) require a JWT bearer token.

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
| Demo (seed/reset/trigger) | `/api/demo` |

Interactive docs at `http://localhost:8000/docs`.
