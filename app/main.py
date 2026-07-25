from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import init_db
from app.api import trips, disruptions, recovery, policies, notifications, demo
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

app.include_router(trips.router,         prefix="/api/trips",         tags=["Trips"])
app.include_router(disruptions.router,   prefix="/api/disruptions",   tags=["Disruptions"])
app.include_router(recovery.router,      prefix="/api/recovery",      tags=["Recovery"])
app.include_router(policies.router,      prefix="/api/policies",      tags=["Policies"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(demo.router,          prefix="/api/demo",          tags=["Demo"])
app.include_router(ws_router)


@app.get("/")
def root():
    return {"service": "ReRoute AI", "status": "running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}
