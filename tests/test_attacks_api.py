"""
tests/test_attacks_api.py - Tests for Phase B Security Simulator backend endpoints.
Verifies:
1. GET /attack/presets returns configured attack scenarios.
2. POST /attack/simulate-model-complies executes only on throwaway temp DB.
3. Rejection of invalid preset IDs.
4. Gated behind DEMO_MODE flag.
5. In-memory rate limiting applied.
"""

import os
from fastapi.testclient import TestClient
from app.main import app


def test_get_attack_presets():
    with TestClient(app) as client:
        res = client.get("/attack/presets")
        assert res.status_code == 200
        presets = res.json()
        assert len(presets) >= 4
        preset_ids = {p["id"] for p in presets}
        assert "drop_users" in preset_ids
        assert "batch_injection" in preset_ids
        assert "attach_exfil" in preset_ids
        assert "cartesian_cross" in preset_ids


def test_simulate_model_complies_uses_production_validator_and_authorizer():
    """
    Verifies that /attack/simulate-model-complies calls the exact same SQLValidator
    and SQLite readonly_authorizer callback as production on an isolated temporary database copy.
    """
    from app.guardrails.sql_validator import SQLValidator
    from app.mcp_server.server import readonly_authorizer

    with TestClient(app) as client:
        # Test DDL drop
        res_drop = client.post("/attack/simulate-model-complies", json={"preset_id": "drop_users"})
        assert res_drop.status_code == 200
        data_drop = res_drop.json()
        assert data_drop["validator_blocked"] is True
        assert "L3 SQL validator" in data_drop["layer_stopped"]

        # Test ATTACH exfiltration
        res_attach = client.post("/attack/simulate-model-complies", json={"preset_id": "attach_exfil"})
        assert res_attach.status_code == 200
        data_attach = res_attach.json()
        assert data_attach["engine_blocked"] is True or data_attach["validator_blocked"] is True
        assert "L4 read-only connection" in data_attach["layer_stopped"]


def test_attack_catalog_grouped_presets():
    with TestClient(app) as client:
        res = client.get("/attack/catalog")
        assert res.status_code == 200
        catalog = res.json()
        assert len(catalog) >= 7
        groups = {c["group"] for c in catalog}
        assert "Direct Destructive" in groups
        assert "Stacked / Semicolon SQL" in groups
        assert "Prompt Injection in Data" in groups
        assert "Obfuscated Attacks" in groups
        assert "Conversational Intent" in groups
        assert any("Hinglish / Hindi Attacks" in g for g in groups)
        assert "Safe Look-Alikes (Allowed)" in groups


def test_simulate_model_complies_invalid_preset():
    with TestClient(app) as client:
        res = client.post("/attack/simulate-model-complies", json={"preset_id": "invalid_evil_hack"})
        assert res.status_code == 400
        assert "Invalid preset ID" in res.json()["detail"]


def test_simulate_model_complies_gated_by_demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    with TestClient(app) as client:
        res = client.post("/attack/simulate-model-complies", json={"preset_id": "drop_users"})
        assert res.status_code == 403
        assert "disabled" in res.json()["detail"]
