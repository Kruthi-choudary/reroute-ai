from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from app.database import init_db
from app.api import trips, disruptions, recovery, policies, notifications, demo, users, auth
from app.core.auth import get_current_user
from app.services.websocket import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ReRoute AI — Travel Disruption Concierge",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth_dep = [Depends(get_current_user)]

app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/api/users",         tags=["Users"],         dependencies=_auth_dep)
app.include_router(trips.router,         prefix="/api/trips",         tags=["Trips"],         dependencies=_auth_dep)
app.include_router(disruptions.router,   prefix="/api/disruptions",   tags=["Disruptions"],   dependencies=_auth_dep)
app.include_router(recovery.router,      prefix="/api/recovery",      tags=["Recovery"],      dependencies=_auth_dep)
app.include_router(policies.router,      prefix="/api/policies",      tags=["Policies"],      dependencies=_auth_dep)
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"], dependencies=_auth_dep)
app.include_router(demo.router,          prefix="/api/demo",          tags=["Demo"])   # open — no auth
app.include_router(ws_router)

app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")


@app.get("/")
def root():
    return {"service": "ReRoute AI", "status": "running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}
