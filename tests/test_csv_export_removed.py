"""
Integration test: Verify CSV export endpoints are removed

This test ensures that all CSV export endpoints have been removed from the API
and return 404 Not Found. This enforces the analytics layer as the single
source of truth for downstream data warehouse consumption.
"""

import pytest
from fastapi.testclient import TestClient


def test_analytics_csv_export_removed(client: TestClient, test_user_with_balance):
    """Verify /analytics/export.csv endpoint returns 404"""
    from datetime import datetime, timedelta, timezone
    
    tok = test_user_with_balance["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    
    # Test with various parameter combinations
    test_cases = [
        # Basic request
        {"period": "30d"},
        # Range-based request
        {
            "from": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
            "to": datetime.now(timezone.utc).isoformat(),
        },
        # With filters
        {
            "period": "7d",
            "request_type": "tailor",
            "model": "gpt-4o",
        },
        # With limit
        {
            "period": "90d",
            "limit": 1000,
        },
    ]
    
    for params in test_cases:
        r = client.get("/analytics/export.csv", params=params, headers=headers)
        assert r.status_code == 404, f"CSV export should return 404, got {r.status_code} for params {params}"


def test_no_csv_content_type_in_analytics_routes(client: TestClient, test_user_with_balance):
    """Verify analytics routes do not return text/csv content type"""
    tok = test_user_with_balance["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    
    # Test valid analytics endpoints
    valid_endpoints = [
        ("/analytics/summary", {"period": "7d", "bucket": "day"}),
        ("/analytics/jobs", {}),
    ]
    
    for endpoint, params in valid_endpoints:
        r = client.get(endpoint, params=params, headers=headers)
        if r.status_code == 200:
            content_type = r.headers.get("content-type", "").lower()
            assert "text/csv" not in content_type, f"{endpoint} should not return text/csv"
            assert "application/csv" not in content_type, f"{endpoint} should not return application/csv"
            # Valid analytics endpoints should return JSON
            assert "application/json" in content_type, f"{endpoint} should return JSON"


def test_export_endpoint_patterns_removed(client: TestClient, test_user_with_balance):
    """Verify common export endpoint patterns are all removed"""
    tok = test_user_with_balance["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    
    # Test various export-related paths that should all 404
    export_paths = [
        "/analytics/export.csv",
        "/analytics/export",
        "/analytics/download",
        "/analytics/download.csv",
        "/export/analytics",
        "/export/analytics.csv",
    ]
    
    for path in export_paths:
        r = client.get(path, headers=headers)
        assert r.status_code in [404, 405], f"{path} should return 404 or 405, got {r.status_code}"


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
def test_csv_export_all_methods_removed(client: TestClient, test_user_with_balance, method):
    """Verify /analytics/export.csv returns 404/405 for all HTTP methods"""
    tok = test_user_with_balance["token"]
    headers = {"Authorization": f"Bearer {tok}"}
    
    request_func = getattr(client, method.lower())
    r = request_func("/analytics/export.csv", headers=headers)
    
    # Should return 404 (not found) or 405 (method not allowed)
    # Either is acceptable - we just want to ensure the endpoint doesn't work
    assert r.status_code in [404, 405], f"{method} /analytics/export.csv should be removed"
