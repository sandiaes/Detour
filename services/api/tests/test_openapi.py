import sys
from pathlib import Path

from fastapi.testclient import TestClient

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT / "scripts"))

from export_openapi import DEFAULT_PATH, contract_text  # noqa: E402


def test_committed_contract_matches_the_application() -> None:
    """Contract drift check. Fix with: python services/api/scripts/export_openapi.py"""
    assert DEFAULT_PATH.read_text(encoding="utf-8") == contract_text()


def test_every_operation_lives_under_v1_and_has_an_operation_id(client: TestClient) -> None:
    spec = client.get("/v1/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert spec["paths"]
    for path, methods in spec["paths"].items():
        assert path.startswith("/v1/"), path
        for operation in methods.values():
            assert operation["operationId"]


def test_no_unversioned_openapi_or_docs(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/docs").status_code == 404
