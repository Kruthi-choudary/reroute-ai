import asyncio
import logging
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.core.logging import configure_logging
from app.database import init_db
from app.api import trips, disruptions, recovery, policies, notifications, demo, users, auth
from app.api.monitor import router as monitor_router
from app.core.auth import get_current_user
from app.services.websocket import router as ws_router
from app.services.flight_monitor import check_active_trips, POLL_INTERVAL_SEC

configure_logging(os.getenv("LOG_LEVEL", "INFO"))
_log = logging.getLogger("app")

POLL_INTERVAL = int(os.getenv("MONITOR_POLL_INTERVAL_SEC", str(POLL_INTERVAL_SEC)))


async def _monitor_loop():
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            await asyncio.to_thread(check_active_trips)
        except Exception as exc:
            _log.error("monitor_loop_error", extra={"error": str(exc)})


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    monitor_task = asyncio.create_task(_monitor_loop())
    yield
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="ReRoute AI — Travel Disruption Concierge",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins_raw = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Demo-Secret"],
    allow_credentials=True,
)

_auth_dep = [Depends(get_current_user)]

app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/api/users",         tags=["Users"],         dependencies=_auth_dep)
app.include_router(trips.router,         prefix="/api/trips",         tags=["Trips"],         dependencies=_auth_dep)
app.include_router(disruptions.router,   prefix="/api/disruptions",   tags=["Disruptions"],   dependencies=_auth_dep)
app.include_router(recovery.router,      prefix="/api/recovery",      tags=["Recovery"],      dependencies=_auth_dep)
app.include_router(policies.router,      prefix="/api/policies",      tags=["Policies"],      dependencies=_auth_dep)
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"], dependencies=_auth_dep)
app.include_router(demo.router,          prefix="/api/demo",          tags=["Demo"])      # open — no auth
app.include_router(monitor_router,       prefix="/monitor",            tags=["Monitor"])   # open — ops visibility
app.include_router(ws_router)

app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")


@app.get("/")
def root():
    return {"service": "ReRoute AI", "status": "running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}
