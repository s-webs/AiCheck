"""API tests (health, no OpenAI calls)."""
import os

import pytest
from fastapi.testclient import TestClient

# Avoid loading .env with real keys in CI
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy")

from api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_available(client):
    r = client.get("/docs")
    assert r.status_code == 200
