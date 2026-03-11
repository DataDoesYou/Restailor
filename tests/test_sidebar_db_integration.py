"""
Test sidebar model selection database integration.

Verifies that sidebar model settings (multi-model mode, fit/tailor/judge selections)
are correctly saved to and retrieved from the user_preferences table.
"""
import pytest
import secrets
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import text

from main import app
from restailor.db import SessionLocal
from restailor.models import User
from restailor import crud, schemas
from restailor.settings_schemas import get_allowed_models


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
    username = f"sidebar_{secrets.token_hex(4)}@example.com"
    
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


@pytest.fixture
def valid_models() -> list[str]:
    """Get list of valid model IDs from allowlist."""
    return list(get_allowed_models())[:3]  # Get first 3 valid models for testing


def test_sidebar_settings_empty_initially(client: TestClient, auth_headers: dict):
    """Test that sidebar settings are empty (defaults) before any changes."""
    response = client.get("/users/me/model-settings", headers=auth_headers)
    
    assert response.status_code == 200
    settings = response.json()["settings"]
    
    # Should have defaults
    assert settings["multi_model_enabled"] is False
    assert settings["fit_models"] == []
    assert settings["tailor_models"] == []
    assert settings["judge_models"] == []


def test_sidebar_save_multi_mode_enabled(client: TestClient, auth_headers: dict, valid_models: list[str]):
    """Test enabling multi-model mode saves to database."""
    model1, model2 = valid_models[0], valid_models[1]
    
    # Enable multi-model mode
    response = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1, model2],
                "tailor_models": [model1],
                "judge_models": [model2],
            }
        },
    )
    
    assert response.status_code == 200
    updated_settings = response.json()["settings"]
    
    assert updated_settings["multi_model_enabled"] is True
    assert model1 in updated_settings["fit_models"]
    assert model2 in updated_settings["fit_models"]
    assert updated_settings["tailor_models"] == [model1]
    assert updated_settings["judge_models"] == [model2]


def test_sidebar_settings_persist_across_requests(client: TestClient, auth_headers: dict, valid_models: list[str]):
    """Test that sidebar settings persist across multiple GET requests."""
    model1, model2 = valid_models[0], valid_models[1]
    
    # Save settings
    client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1],
                "tailor_models": [model2],
                "judge_models": [model1],
            }
        },
    )
    
    # Fetch settings multiple times
    for _ in range(3):
        response = client.get("/users/me/model-settings", headers=auth_headers)
        assert response.status_code == 200
        settings = response.json()["settings"]
        
        assert settings["multi_model_enabled"] is True
        assert settings["fit_models"] == [model1]
        assert settings["tailor_models"] == [model2]
        assert settings["judge_models"] == [model1]


def test_sidebar_toggle_multi_mode_off(client: TestClient, auth_headers: dict, valid_models: list[str]):
    """Test toggling multi-model mode off."""
    model1, model2 = valid_models[0], valid_models[1]
    
    # Enable first
    client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1, model2],
            }
        },
    )
    
    # Disable multi-mode
    response = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": False,
                "fit_models": [model1, model2],  # Keep selections
            }
        },
    )
    
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["multi_model_enabled"] is False
    # Model selections should persist even when multi-mode is off
    assert settings["fit_models"] == [model1, model2]


def test_sidebar_update_model_selections(client: TestClient, auth_headers: dict, valid_models: list[str]):
    """Test updating individual model selections."""
    model1, model2 = valid_models[0], valid_models[1]
    
    # Initial selection
    client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1],
            }
        },
    )
    
    # Update to add more models
    response = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1, model2, valid_models[2]],
            }
        },
    )
    
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert len(settings["fit_models"]) == 3
    assert valid_models[2] in settings["fit_models"]


def test_sidebar_empty_model_arrays(client: TestClient, auth_headers: dict):
    """Test that empty model arrays are handled correctly."""
    response = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [],
                "tailor_models": [],
                "judge_models": [],
            }
        },
    )
    
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["fit_models"] == []
    assert settings["tailor_models"] == []
    assert settings["judge_models"] == []


def test_sidebar_partial_update(client: TestClient, auth_headers: dict, valid_models: list[str]):
    """Test partial updates (only updating some fields)."""
    model1, model2, model3 = valid_models[0], valid_models[1], valid_models[2]
    
    # Initial full settings
    client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1],
                "tailor_models": [model2],
                "judge_models": [model3],
            }
        },
    )
    
    # Update only fit_models (partial update)
    response = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model2],  # Changed
                "tailor_models": [model2],  # Unchanged
                "judge_models": [model3],  # Unchanged
            }
        },
    )
    
    assert response.status_code == 200
    settings = response.json()["settings"]
    assert settings["fit_models"] == [model2]
    assert settings["tailor_models"] == [model2]
    assert settings["judge_models"] == [model3]


def test_sidebar_optimistic_locking(client: TestClient, auth_headers: dict, valid_models: list[str]):
    """Test optimistic locking prevents concurrent modification conflicts."""
    model1, model2, model3 = valid_models[0], valid_models[1], valid_models[2]
    
    # Initial save
    response1 = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1],
            }
        },
    )
    updated_at = response1.json()["settings"]["updated_at"]
    
    # Valid update with correct timestamp
    response2 = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": False,
                "fit_models": [model2],
            },
            "expectedUpdatedAt": updated_at,
        },
    )
    assert response2.status_code == 200
    
    # Try to update with stale timestamp (simulating concurrent modification)
    response3 = client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model3],
            },
            "expectedUpdatedAt": updated_at,  # Stale!
        },
    )
    assert response3.status_code == 409
    assert "conflict" in response3.json()["detail"].lower()


def test_sidebar_database_row_created(client: TestClient, auth_headers: dict, test_user: User, db: Session, valid_models: list[str]):
    """Test that a row is actually created in user_preferences table."""
    model1 = valid_models[0]
    
    # Save settings
    client.put(
        "/users/me/model-settings",
        headers=auth_headers,
        json={
            "settings": {
                "multi_model_enabled": True,
                "fit_models": [model1],
            }
        },
    )
    
    # Query database directly
    result = db.execute(
        text("""
            SELECT settings->>'multi_model_enabled' as multi_mode,
                   settings->'fit_models' as fit_models
            FROM user_preferences
            WHERE user_id = :user_id
        """),
        {"user_id": test_user.id}
    ).fetchone()
    
    assert result is not None
    assert result[0] == "true"  # JSONB boolean as string
    assert model1 in str(result[1])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
