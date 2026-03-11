"""Tests for user settings API endpoints."""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from restailor.db import SessionLocal
from restailor.models import User, UserPreferences
from restailor.settings_schemas import get_allowed_models
from restailor import crud, schemas


@pytest.fixture
def db():
    """Create a test database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_user(db: Session) -> User:
    """Create a test user."""
    import secrets
    username = f"testuser_{secrets.token_hex(4)}@example.com"
    
    user_data = schemas.UserCreate(username=username, password="testpass123")
    user = crud.create_user(db, user_data)
    # Mark as verified and test
    user.is_verified = True
    user.is_test = True
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client() -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers(test_user: User, client: TestClient) -> dict[str, str]:
    """Get authentication headers for test user."""
    response = client.post(
        "/token",
        data={"username": test_user.username, "password": "testpass123"}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_settings_no_preferences(client: TestClient, auth_headers: dict, test_user: User):
    """Test GET /users/me/model-settings when no preferences exist."""
    response = client.get("/users/me/model-settings", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "settings" in data
    settings = data["settings"]
    
    # Should return defaults
    assert settings["multi_model_enabled"] is False
    assert settings["fit_models"] == []
    assert settings["tailor_models"] == []
    assert settings["judge_models"] == []
    assert settings["last_single_fit"] is None
    assert settings["last_single_tailor"] is None
    assert settings["last_single_judge"] is None
    assert settings["version"] == 1


def test_get_settings_unauthorized(client: TestClient):
    """Test GET /users/me/model-settings without authentication."""
    response = client.get("/users/me/model-settings")
    assert response.status_code == 401


def test_put_settings_valid(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    """Test PUT /users/me/model-settings with valid data."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    valid_model = allowed[0]
    
    request_body = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": [valid_model],
            "tailor_models": [valid_model],
            "judge_models": [],
            "last_single_fit": valid_model,
            "last_single_tailor": None,
            "last_single_judge": None,
            "version": 1,
        }
    }
    
    response = client.put("/users/me/model-settings", headers=auth_headers, json=request_body)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "settings" in data
    assert "message" in data
    assert data["message"] == "Settings updated successfully"
    
    settings = data["settings"]
    assert settings["multi_model_enabled"] is True
    assert settings["fit_models"] == [valid_model]
    assert settings["tailor_models"] == [valid_model]
    assert settings["last_single_fit"] == valid_model
    assert "updated_at" in settings
    assert settings["updated_at"] is not None
    
    # Verify stored in database
    prefs = db.query(UserPreferences).filter_by(user_id=test_user.id).first()
    assert prefs is not None
    assert prefs.settings["fit_models"] == [valid_model]


def test_put_settings_invalid_model(client: TestClient, auth_headers: dict):
    """Test PUT /users/me/model-settings with invalid model ID.
    
    Pydantic validation errors return 422 (FastAPI standard for request validation failures).
    """
    request_body = {
        "settings": {
            "multi_model_enabled": False,
            "fit_models": [],
            "tailor_models": [],
            "judge_models": [],
            "last_single_tailor": "fake-model-999",
            "version": 1,
        }
    }
    
    response = client.put("/users/me/model-settings", headers=auth_headers, json=request_body)
    
    # FastAPI returns 422 for Pydantic validation errors
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    # Check that the error message mentions the invalid model
    assert any("fake-model-999" in str(err) for err in data["detail"])


def test_put_settings_injection_attempt(client: TestClient, auth_headers: dict):
    """Test PUT /users/me/model-settings with injection attempts.
    
    Pydantic validation errors return 422 (FastAPI standard).
    """
    malicious_inputs = [
        "'; DROP TABLE users; --",
        "../../../etc/passwd",
        "<script>alert('xss')</script>",
    ]
    
    for malicious in malicious_inputs:
        request_body = {
            "settings": {
                "multi_model_enabled": False,
                "fit_models": [],
                "tailor_models": [],
                "judge_models": [],
                "last_single_fit": malicious,
                "version": 1,
            }
        }
        
        response = client.put("/users/me/model-settings", headers=auth_headers, json=request_body)
        # FastAPI returns 422 for Pydantic validation errors
        assert response.status_code == 422, f"Should reject malicious input: {malicious}"


def test_put_settings_unauthorized(client: TestClient):
    """Test PUT /users/me/model-settings without authentication."""
    request_body = {
        "settings": {
            "multi_model_enabled": False,
            "fit_models": [],
            "tailor_models": [],
            "judge_models": [],
            "version": 1,
        }
    }
    
    response = client.put("/users/me/model-settings", json=request_body)
    assert response.status_code == 401


def test_put_settings_optimistic_lock_success(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    """Test optimistic locking - update with matching timestamp succeeds."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    # First, create initial settings
    initial_body = {
        "settings": {
            "multi_model_enabled": False,
            "fit_models": [],
            "tailor_models": [],
            "judge_models": [],
            "last_single_fit": allowed[0],
            "version": 1,
        }
    }
    
    response1 = client.put("/users/me/model-settings", headers=auth_headers, json=initial_body)
    assert response1.status_code == 200
    initial_updated_at = response1.json()["settings"]["updated_at"]
    
    # Update with correct timestamp should succeed
    update_body = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": [allowed[0]],
            "tailor_models": [],
            "judge_models": [],
            "last_single_fit": allowed[0],
            "version": 1,
        },
        "expectedUpdatedAt": initial_updated_at,
    }
    
    response2 = client.put("/users/me/model-settings", headers=auth_headers, json=update_body)
    assert response2.status_code == 200
    assert response2.json()["settings"]["multi_model_enabled"] is True


def test_put_settings_optimistic_lock_conflict(client: TestClient, auth_headers: dict, test_user: User, db: Session):
    """Test optimistic locking - update with stale timestamp fails with 409."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    # Create initial settings
    initial_body = {
        "settings": {
            "multi_model_enabled": False,
            "fit_models": [],
            "tailor_models": [],
            "judge_models": [],
            "last_single_fit": allowed[0],
            "version": 1,
        }
    }
    
    response1 = client.put("/users/me/model-settings", headers=auth_headers, json=initial_body)
    assert response1.status_code == 200
    old_timestamp = response1.json()["settings"]["updated_at"]
    
    # Make another update (simulating concurrent modification)
    update1_body = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": [allowed[0]],
            "tailor_models": [],
            "judge_models": [],
            "version": 1,
        }
    }
    
    response2 = client.put("/users/me/model-settings", headers=auth_headers, json=update1_body)
    assert response2.status_code == 200
    
    # Try to update with stale timestamp - should get 409
    stale_update_body = {
        "settings": {
            "multi_model_enabled": False,
            "fit_models": [],
            "tailor_models": [allowed[0]],
            "judge_models": [],
            "version": 1,
        },
        "expectedUpdatedAt": old_timestamp,  # Stale!
    }
    
    response3 = client.put("/users/me/model-settings", headers=auth_headers, json=stale_update_body)
    assert response3.status_code == 409
    data = response3.json()
    assert "detail" in data
    assert "conflict" in data["detail"].lower()


def test_get_then_put_round_trip(client: TestClient, auth_headers: dict, test_user: User):
    """Test GET -> PUT round trip workflow."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    # Get default settings
    response1 = client.get("/users/me/model-settings", headers=auth_headers)
    assert response1.status_code == 200
    
    # Update settings
    new_settings = response1.json()["settings"]
    new_settings["multi_model_enabled"] = True
    new_settings["fit_models"] = [allowed[0]]
    
    response2 = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={"settings": new_settings}
    )
    assert response2.status_code == 200
    
    # Get again to verify
    response3 = client.get("/users/me/model-settings", headers=auth_headers)
    assert response3.status_code == 200
    retrieved = response3.json()["settings"]
    
    assert retrieved["multi_model_enabled"] is True
    assert retrieved["fit_models"] == [allowed[0]]


def test_put_settings_multiple_models(client: TestClient, auth_headers: dict):
    """Test storing multiple models in lists."""
    allowed = list(get_allowed_models())
    if len(allowed) < 2:
        pytest.skip("Need at least 2 models in allowlist")
    
    request_body = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": [allowed[0], allowed[1]],
            "tailor_models": [allowed[0]],
            "judge_models": [allowed[1]],
            "version": 1,
        }
    }
    
    response = client.put("/users/me/model-settings", headers=auth_headers, json=request_body)
    assert response.status_code == 200
    
    settings = response.json()["settings"]
    assert len(settings["fit_models"]) == 2
    assert allowed[0] in settings["fit_models"]
    assert allowed[1] in settings["fit_models"]


def test_put_settings_mixed_valid_invalid(client: TestClient, auth_headers: dict):
    """Test that mixing valid and invalid models fails.
    
    Pydantic validation errors return 422 (FastAPI standard).
    """
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    request_body = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": [allowed[0], "fake-model-999"],
            "tailor_models": [],
            "judge_models": [],
            "version": 1,
        }
    }
    
    response = client.put("/users/me/model-settings", headers=auth_headers, json=request_body)
    # FastAPI returns 422 for Pydantic validation errors
    assert response.status_code == 422


def test_put_settings_empty_lists(client: TestClient, auth_headers: dict):
    """Test storing empty model lists (valid scenario)."""
    request_body = {
        "settings": {
            "multi_model_enabled": True,
            "fit_models": [],
            "tailor_models": [],
            "judge_models": [],
            "version": 1,
        }
    }
    
    response = client.put("/users/me/model-settings", headers=auth_headers, json=request_body)
    assert response.status_code == 200
    
    settings = response.json()["settings"]
    assert settings["fit_models"] == []
    assert settings["tailor_models"] == []
    assert settings["judge_models"] == []


def test_put_settings_updates_timestamp(client: TestClient, auth_headers: dict):
    """Test that PUT updates the updated_at timestamp."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    # First update
    response1 = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={"settings": {"fit_models": [allowed[0]], "version": 1}}
    )
    assert response1.status_code == 200
    timestamp1 = response1.json()["settings"]["updated_at"]
    
    # Wait a tiny bit and update again
    import time
    time.sleep(0.1)
    
    # Second update
    response2 = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={"settings": {"fit_models": [], "version": 1}}
    )
    assert response2.status_code == 200
    timestamp2 = response2.json()["settings"]["updated_at"]
    
    # Timestamps should be different
    assert timestamp1 != timestamp2
