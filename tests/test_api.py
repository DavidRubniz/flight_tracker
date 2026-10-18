from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from flight_tracker.api import create_app
from flight_tracker.config import Config


@pytest.fixture
def client(config: Config) -> Iterator[TestClient]:
    with TestClient(create_app(config, start_scheduler=False)) as test_client:
        yield test_client


def test_index_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Flight Tracker" in response.text


def test_destination_lifecycle(client: TestClient) -> None:
    created = client.post("/api/destinations", json={"code": "mxp", "target_price": 200})
    assert created.status_code == 201
    dest_id = created.json()["id"]

    assert client.post("/api/destinations", json={"code": "MXP"}).status_code == 409
    assert client.post("/api/destinations", json={"code": "TOOLONG"}).status_code == 422

    patched = client.patch(f"/api/destinations/{dest_id}", json={"max_stops": 0, "max_duration_hours": 10})
    assert patched.json()["max_stops"] == 0
    assert patched.json()["max_duration_hours"] == 10
    too_long = client.patch(f"/api/destinations/{dest_id}", json={"max_duration_hours": 100})
    assert too_long.status_code == 422

    assert client.delete(f"/api/destinations/{dest_id}").status_code == 204
    assert client.delete(f"/api/destinations/{dest_id}").status_code == 404


def test_settings_validation(client: TestClient) -> None:
    assert client.put("/api/settings", json={"scan_interval_hours": 0}).status_code == 422
    ok = client.put("/api/settings", json={"scan_interval_hours": 3, "scheduler_enabled": False})
    assert ok.status_code == 200
    assert client.get("/api/settings").json()["scan_interval_hours"] == 3


def test_scan_then_dashboard(client: TestClient) -> None:
    # TestClient runs background tasks before returning the response.
    assert client.post("/api/scan").json()["accepted"] is True
    rows = client.get("/api/dashboard").json()
    assert rows
    assert all(r["current_price"] is not None for r in rows if r["destination"]["enabled"])
    assert client.get("/api/offers").json()
