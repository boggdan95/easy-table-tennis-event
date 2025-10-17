"""Smoke tests for web application."""

import pytest
from fastapi.testclient import TestClient

from ettem.webapp.app import app


def test_index_returns_200():
    """Test that index route returns 200 status."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
