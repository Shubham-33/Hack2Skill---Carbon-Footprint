"""Shared fixtures. Pins config to the offline/default state before each test so
cases opt into NVIDIA or Sheets explicitly via monkeypatch."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import app as app_module  # noqa: E402


@pytest.fixture
def app_mod():
    return app_module


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Each test starts offline, no Sheet, empty in-memory ledger."""
    app_module._MEMORY_LEDGER.clear()
    monkeypatch.setattr(app_module, "NVIDIA_API_KEY", "")
    monkeypatch.setattr(app_module, "SHEET_ID", "")
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", raising=False)
    yield
    app_module._MEMORY_LEDGER.clear()


class FakeResp:
    """Minimal stand-in for a requests.Response."""

    def __init__(self, payload, raise_exc=None):
        self._payload = payload
        self._raise = raise_exc

    def raise_for_status(self):
        if self._raise:
            raise self._raise

    def json(self):
        return self._payload
