"""Tests for the FastAPI endpoints."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from starlette.testclient import TestClient
from api.index import app


client = TestClient(app)


def test_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


def test_health_fields():
    resp = client.get("/api/health")
    data = resp.json()
    assert set(data.keys()) == {"status", "version", "timestamp"}


def test_search_requires_query():
    """Search endpoint should reject missing query param."""
    resp = client.get("/api/search")
    assert resp.status_code == 422  # validation error


def test_search_rejects_short_query():
    """Search query must be >= 2 chars."""
    resp = client.get("/api/search", params={"q": "x"})
    assert resp.status_code == 422


def test_cors_headers():
    """CORS middleware should set headers on preflight."""
    resp = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers
