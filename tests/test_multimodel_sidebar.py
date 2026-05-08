"""
Test multi-model sidebar functionality.

Verifies:
- Multi-model toggle saves and loads correctly
- Single-model selections save as plain model_ids
- Multi-model arrays save as plain model_ids  
- Transitioning between modes preserves selections
- Multi-mode with 1 model still sets the flag correctly
"""
import uuid
import pytest
from fastapi.testclient import TestClient
import sqlalchemy as sa
from main import app
from restailor.db import SessionLocal
from tests.utils import signup_and_mark_test, login


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


pytestmark = pytest.mark.critical


def test_multimodel_toggle_saves_correctly(client: TestClient):
    """Test that multi-model toggle state persists correctly."""
    email = f"multi_{uuid.uuid4().hex[:8]}@test.com"
    signup_and_mark_test(client, email)
    token = login(client, email)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}
    
    # 1. Enable multi-model mode
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": True,
            "fit_models": ["gpt-5.4-mini"],
            "tailor_models": ["claude-sonnet-4-6"],
            "judge_models": ["grok-4.3"],
            "last_single_fit": "gpt-5.4-mini",
            "last_single_tailor": "claude-sonnet-4-6",
            "last_single_judge": "grok-4.3"
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # 2. Verify it loads correctly
    resp = client.get("/users/me/model-settings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    settings = data.get("settings", data)
    
    assert settings["multi_model_enabled"] is True
    assert settings["fit_models"] == ["gpt-5.4-mini"]
    assert settings["tailor_models"] == ["claude-sonnet-4-6"]
    assert settings["judge_models"] == ["grok-4.3"]


def test_multimodel_with_single_selection_no_colons(client: TestClient):
    """Test that multi-model with 1 model selected saves plain model_id."""
    email = f"multi_{uuid.uuid4().hex[:8]}@test.com"
    signup_and_mark_test(client, email)
    token = login(client, email)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}
    
    # Save multi-model mode with only 1 model selected
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": True,
            "fit_models": ["claude-sonnet-4-6"],  # Only 1 model
            "tailor_models": ["gpt-5.5"],
            "judge_models": ["grok-4.3"],
            "last_single_fit": "gpt-5.4-mini",
            "last_single_tailor": "claude-sonnet-4-6",
            "last_single_judge": "grok-4.3"
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # Verify no colons in model IDs
    resp = client.get("/users/me/model-settings", headers=headers)
    data = resp.json()
    settings = data.get("settings", data)
    
    for model_id in settings["fit_models"]:
        assert ":" not in model_id, f"Found colon in fit_models: {model_id}"
    for model_id in settings["tailor_models"]:
        assert ":" not in model_id, f"Found colon in tailor_models: {model_id}"
    for model_id in settings["judge_models"]:
        assert ":" not in model_id, f"Found colon in judge_models: {model_id}"


def test_multimodel_with_multiple_selections(client: TestClient):
    """Test that multi-model with multiple models saves all as plain model_ids."""
    email = f"multi_{uuid.uuid4().hex[:8]}@test.com"
    signup_and_mark_test(client, email)
    token = login(client, email)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}
    
    # Save multi-model mode with multiple models
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": True,
            "fit_models": ["gpt-5.4-mini", "claude-sonnet-4-6", "grok-4.3"],
            "tailor_models": ["gpt-5.5", "claude-opus-4-7"],
            "judge_models": ["grok-4.3"],
            "last_single_fit": "gpt-5.4-mini",
            "last_single_tailor": "gpt-5.5",
            "last_single_judge": "grok-4.3"
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # Verify all model_ids are plain (no colons)
    resp = client.get("/users/me/model-settings", headers=headers)
    data = resp.json()
    settings = data.get("settings", data)
    
    assert len(settings["fit_models"]) == 3
    assert len(settings["tailor_models"]) == 2
    assert len(settings["judge_models"]) == 1
    
    all_models = settings["fit_models"] + settings["tailor_models"] + settings["judge_models"]
    for model_id in all_models:
        assert ":" not in model_id, f"Found colon in model_id: {model_id}"


def test_toggle_from_single_to_multi_mode(client: TestClient):
    """Test transitioning from single-model to multi-model mode."""
    email = f"multi_{uuid.uuid4().hex[:8]}@test.com"
    signup_and_mark_test(client, email)
    token = login(client, email)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}
    
    # 1. Start in single-model mode
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": False,
            "last_single_fit": "gpt-5.4-mini",
            "last_single_tailor": "claude-sonnet-4-6",
            "last_single_judge": "grok-4.3",
            "fit_models": [],
            "tailor_models": [],
            "judge_models": []
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # 2. Toggle to multi-model mode (sidebar seeds arrays from single selections)
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": True,
            "fit_models": ["gpt-5.4-mini"],  # Seeded from last_single_fit
            "tailor_models": ["claude-sonnet-4-6"],
            "judge_models": ["grok-4.3"],
            "last_single_fit": "gpt-5.4-mini",
            "last_single_tailor": "claude-sonnet-4-6",
            "last_single_judge": "grok-4.3"
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # 3. Verify multi-mode is enabled and arrays are populated
    resp = client.get("/users/me/model-settings", headers=headers)
    data = resp.json()
    settings = data.get("settings", data)
    
    assert settings["multi_model_enabled"] is True
    assert "gpt-5.4-mini" in settings["fit_models"]
    assert "claude-sonnet-4-6" in settings["tailor_models"]
    assert "grok-4.3" in settings["judge_models"]


def test_toggle_from_multi_to_single_mode(client: TestClient):
    """Test transitioning from multi-model to single-model mode."""
    email = f"multi_{uuid.uuid4().hex[:8]}@test.com"
    signup_and_mark_test(client, email)
    token = login(client, email)
    headers = {"Authorization": f"Bearer {token}", "Origin": "http://localhost:3000"}
    
    # 1. Start in multi-model mode with multiple selections
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": True,
            "fit_models": ["gpt-5.4-mini", "claude-sonnet-4-6"],
            "tailor_models": ["grok-4.3"],
            "judge_models": ["claude-opus-4-7"],
            "last_single_fit": "gpt-5.4-mini",
            "last_single_tailor": "grok-4.3",
            "last_single_judge": "claude-opus-4-7"
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # 2. Toggle to single-model mode (sidebar uses first model from array)
    resp = client.put("/users/me/model-settings", json={
        "settings": {
            "multi_model_enabled": False,
            "last_single_fit": "gpt-5.4-mini",  # First from fit_models
            "last_single_tailor": "grok-4.3",  # First from tailor_models
            "last_single_judge": "claude-opus-4-7",  # First from judge_models
            "fit_models": ["gpt-5.4-mini", "claude-sonnet-4-6"],  # Preserved
            "tailor_models": ["grok-4.3"],
            "judge_models": ["claude-opus-4-7"]
        }
    }, headers=headers)
    assert resp.status_code == 200
    
    # 3. Verify single-mode is enabled and single selections are set
    resp = client.get("/users/me/model-settings", headers=headers)
    data = resp.json()
    settings = data.get("settings", data)
    
    assert settings["multi_model_enabled"] is False
    assert settings["last_single_fit"] == "gpt-5.4-mini"
    assert settings["last_single_tailor"] == "grok-4.3"
    assert settings["last_single_judge"] == "claude-opus-4-7"

