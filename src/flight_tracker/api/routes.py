"""REST endpoints consumed by the web UI (``/api/...``)."""

from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel

from flight_tracker.api.container import ContainerDep
from flight_tracker.models import (
    AlertRecord,
    AppSettings,
    DashboardRow,
    Destination,
    DestinationCreate,
    DestinationUpdate,
    PricePoint,
    ScanStatus,
    StoredOffer,
)
from flight_tracker.notifications import Notification
from flight_tracker.regions import AIRPORT_NAMES, REGIONS
from flight_tracker.services.dashboard import build_dashboard

router = APIRouter(prefix="/api")


class Meta(BaseModel):
    provider: str
    origin: str
    currency: str
    regions: dict[str, dict[str, Any]]
    airport_names: dict[str, str]
    channels: dict[str, bool]


class Accepted(BaseModel):
    accepted: bool
    message: str


def _not_found(destination_id: int) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"Destination {destination_id} not found")


# ---------------------------------------------------------------------- meta & dashboard


@router.get("/meta")
def get_meta(c: ContainerDep) -> Meta:
    return Meta(
        provider=c.provider.name,
        origin=c.config.origin_airport,
        currency=c.config.currency,
        regions={k: {"name": r.name, "airports": list(r.airports)} for k, r in REGIONS.items()},
        airport_names=AIRPORT_NAMES,
        channels=c.notifier.available_channels,
    )


@router.get("/dashboard")
def get_dashboard(c: ContainerDep) -> list[DashboardRow]:
    return build_dashboard(c.db)


@router.get("/offers")
def get_offers(
    c: ContainerDep,
    destination_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 60,
) -> list[StoredOffer]:
    return c.db.latest_offers(destination_id, limit)


@router.get("/alerts")
def get_alerts(c: ContainerDep, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[AlertRecord]:
    return c.db.list_alerts(limit)


# ---------------------------------------------------------------------- destinations


@router.get("/destinations")
def list_destinations(c: ContainerDep) -> list[Destination]:
    return c.db.list_destinations()


@router.post("/destinations", status_code=status.HTTP_201_CREATED)
def create_destination(c: ContainerDep, body: DestinationCreate) -> Destination:
    try:
        return c.db.add_destination(body)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{body.code} is already tracked") from exc


@router.patch("/destinations/{destination_id}")
def update_destination(c: ContainerDep, destination_id: int, body: DestinationUpdate) -> Destination:
    updated = c.db.update_destination(destination_id, body)
    if updated is None:
        raise _not_found(destination_id)
    return updated


@router.delete("/destinations/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_destination(c: ContainerDep, destination_id: int) -> None:
    if not c.db.delete_destination(destination_id):
        raise _not_found(destination_id)


@router.get("/destinations/{destination_id}/history")
def get_history(
    c: ContainerDep, destination_id: int, days: Annotated[int, Query(ge=1, le=365)] = 30
) -> list[PricePoint]:
    if c.db.get_destination(destination_id) is None:
        raise _not_found(destination_id)
    return c.db.price_history(destination_id, days)


# ---------------------------------------------------------------------- settings


@router.get("/settings")
def get_settings(c: ContainerDep) -> AppSettings:
    return c.db.get_settings()


@router.put("/settings")
def put_settings(c: ContainerDep, body: AppSettings) -> AppSettings:
    saved = c.db.save_settings(body)
    c.scheduler.apply(saved)
    return saved


# ---------------------------------------------------------------------- scanning


@router.get("/status")
def get_status(c: ContainerDep) -> ScanStatus:
    return c.tracker.status.model_copy(update={"next_run": c.scheduler.next_run})


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
async def start_scan(c: ContainerDep, tasks: BackgroundTasks) -> Accepted:
    if c.tracker.is_running:
        return Accepted(accepted=False, message="סריקה כבר רצה")
    tasks.add_task(c.tracker.scan_all)
    return Accepted(accepted=True, message="הסריקה התחילה")


@router.post("/scan/{destination_id}", status_code=status.HTTP_202_ACCEPTED)
async def start_scan_one(c: ContainerDep, destination_id: int, tasks: BackgroundTasks) -> Accepted:
    if c.db.get_destination(destination_id) is None:
        raise _not_found(destination_id)
    if c.tracker.is_running:
        return Accepted(accepted=False, message="סריקה כבר רצה")
    tasks.add_task(c.tracker.scan_one, destination_id)
    return Accepted(accepted=True, message="הסריקה התחילה")


@router.post("/notifications/test")
async def test_notifications(c: ContainerDep) -> dict[str, str]:
    return await c.notifier.dispatch(
        Notification(title="✈ Flight Tracker", body="זוהי התראת בדיקה - ההתראות עובדות!")
    )
