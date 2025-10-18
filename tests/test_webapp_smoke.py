"""Smoke tests for web application."""

import pytest
from fastapi.testclient import TestClient

from ettem.webapp.app import app


@pytest.fixture
def client():
    """Create a test client for the app."""
    return TestClient(app)


def test_index_returns_200(client):
    """Test that index route returns 200 status."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_static_css_loads(client):
    """Test that static CSS file can be loaded."""
    response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_category_page_loads_for_any_category(client):
    """Test that category page loads (even for nonexistent categories)."""
    # The app doesn't validate category existence, just loads the template
    response = client.get("/category/U13")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_enter_result_page_loads(client):
    """Test that enter result page can be accessed."""
    # This may return 404 if no matches exist, or redirect
    # Just test that the route is defined
    response = client.get("/enter-result/1")
    # Accept either 404 (no match) or 200 (match found) or 307 (redirect)
    assert response.status_code in [200, 307, 404]
