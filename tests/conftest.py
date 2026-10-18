from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from flight_tracker.config import Config, ProviderName
from flight_tracker.database import Database


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(_env_file=None, data_dir=tmp_path, flight_provider=ProviderName.MOCK)  # type: ignore[call-arg]


@pytest.fixture
def db(config: Config) -> Iterator[Database]:
    database = Database(config.db_path)
    yield database
    database.close()
