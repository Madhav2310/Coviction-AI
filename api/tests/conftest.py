"""Shared fixtures for Coviction tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def observation_id():
    return uuid.uuid4()


@pytest.fixture
def mock_observation(observation_id):
    obs = MagicMock()
    obs.id = observation_id
    obs.title = "Met Abhi sir at demo day"
    obs.body = "Abhi sir is building an AI infra tool. Talked to Dr Mehta from Sequoia too."
    obs.voice_transcript = ""
    obs.image_summary = ""
    obs.sector_tags = ["ai"]
    obs.created_at = datetime.now(timezone.utc)
    return obs


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db
