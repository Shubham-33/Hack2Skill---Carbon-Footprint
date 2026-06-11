"""Full-coverage tests for Sprout. All network (NVIDIA, Sheets) is mocked."""
import json

import pytest
import requests

from tests.conftest import FakeResp

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_gauge_levels(app_mod):
    assert app_mod.gauge_status(3.0)["level"] == "green"
    assert app_mod.gauge_status(6.0)["level"] == "amber"
    assert app_mod.gauge_status(12.0)["level"] == "red"


def test_equivalence_branches(app_mod):
    assert "km driven" in app_mod.equivalence(5.0)
    assert "smartphone charges" in app_mod.equivalence(0.01)


def test_extract_json_variants(app_mod):
    assert app_mod._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert app_mod._extract_json('here: {"b": 2} done') == {"b": 2}
    with pytest.raises(ValueError):
        app_mod._extract_json("no json here")


def test_offline_estimate_with_keywords(app_mod):
    out = app_mod.offline_estimate("Drove 20 km, had a beef burger, ran the AC 3 hours")
    assert out["source"] == "offline"
    assert out["total_kg"] > 0
    assert out["swap"]["tip"]
    labels = {i["label"] for i in out["items"]}
    assert "drove" in labels and "beef" in labels


def test_offline_estimate_no_keywords_defaults(app_mod):
    out = app_mod.offline_estimate("just chilled at home")
    assert out["items"][0]["category"] == "general"
    assert out["total_kg"] == 5.0


def test_first_number_near_default(app_mod):
    # "train" (distance unit) with no adjacent number -> _first_number_near defaults to 1
    item = next(i for i in app_mod.offline_estimate("took the train")["items"] if i["label"] == "train")
    assert item["amount"] == 1.0


def test_offline_estimate_keeps_biggest_per_category(app_mod):
    # "beef burger" both match food; only the larger (beef, 6kg) is kept, no double count.
    out = app_mod.offline_estimate("had a beef burger")
    food = [i for i in out["items"] if i["category"] == "food"]
    assert len(food) == 1 and food[0]["label"] == "beef"


# ---------------------------------------------------------------------------
# NVIDIA client + analyze_day
# ---------------------------------------------------------------------------

def test_nvidia_chat_returns_content(app_mod, monkeypatch):
    payload = {"choices": [{"message": {"content": "hi"}}]}
    monkeypatch.setattr(app_mod.requests, "post", lambda *a, **k: FakeResp(payload))
    assert app_mod.nvidia_chat("sys", "user") == "hi"


def test_analyze_day_offline_when_no_key(app_mod):
    assert app_mod.analyze_day("drove 10 km")["source"] == "offline"


VALID_ANALYSIS = json.dumps(
    {
        "items": [{"label": "car", "category": "transport", "amount": 10, "unit": "km", "kg": 1.7}],
        "total_kg": 1.7,
        "swap": {"tip": "carpool", "kg_saved": 1.0, "money_inr": 50, "category": "transport"},
        "summary": "small day",
    }
)


def test_analyze_day_nvidia_success(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    monkeypatch.setattr(app_mod, "nvidia_chat", lambda s, u: VALID_ANALYSIS)
    out = app_mod.analyze_day("drove 10 km")
    assert out["source"] == "nvidia"
    assert out["swap"]["tip"] == "carpool"


def test_analyze_day_nvidia_network_error_falls_back(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")

    def boom(s, u):
        raise requests.RequestException("down")

    monkeypatch.setattr(app_mod, "nvidia_chat", boom)
    assert app_mod.analyze_day("drove 10 km")["source"] == "offline"


def test_analyze_day_nvidia_bad_shape_falls_back(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    monkeypatch.setattr(app_mod, "nvidia_chat", lambda s, u: '{"unexpected": true}')
    assert app_mod.analyze_day("drove 10 km")["source"] == "offline"


# ---------------------------------------------------------------------------
# whatif
# ---------------------------------------------------------------------------

def test_whatif_offline_when_no_key(app_mod):
    out = app_mod.whatif("bike to work")
    assert out["source"] == "offline"
    assert out["annual_kg"] == 180.0


def test_whatif_nvidia_success_fills_trees(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    payload = json.dumps({"annual_kg": 210, "annual_money_inr": 4000, "note": "go"})
    monkeypatch.setattr(app_mod, "nvidia_chat", lambda s, u: payload)
    out = app_mod.whatif("bike")
    assert out["source"] == "nvidia"
    assert out["trees"] == 10.0


def test_whatif_nvidia_error_falls_back(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")

    def boom(s, u):
        raise requests.RequestException("x")

    monkeypatch.setattr(app_mod, "nvidia_chat", boom)
    assert app_mod.whatif("bike")["source"] == "offline"


# ---------------------------------------------------------------------------
# sheets_enabled
# ---------------------------------------------------------------------------

def test_sheets_disabled_without_sheet_id(app_mod):
    assert app_mod.sheets_enabled() is False


def test_sheets_enabled_with_inline_creds(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "SHEET_ID", "sid")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON_CONTENT", "{}")
    assert app_mod.sheets_enabled() is True


def test_sheets_enabled_with_creds_file(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "SHEET_ID", "sid")
    monkeypatch.setattr(app_mod.os.path, "exists", lambda p: True)
    assert app_mod.sheets_enabled() is True


def test_sheets_disabled_when_no_creds_anywhere(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "SHEET_ID", "sid")
    monkeypatch.setattr(app_mod.os.path, "exists", lambda p: False)
    assert app_mod.sheets_enabled() is False


# ---------------------------------------------------------------------------
# ledger_append / ledger_state
# ---------------------------------------------------------------------------

def test_ledger_append_memory(app_mod):
    app_mod.ledger_append("g1", "alice", 3.0, 90.0)
    assert app_mod._MEMORY_LEDGER["g1"][0]["member"] == "alice"


def test_ledger_append_sheets_success(app_mod, monkeypatch):
    class Sess:
        def __init__(self):
            self.called = False

        def post(self, *a, **k):
            self.called = True
            return FakeResp({})

    sess = Sess()
    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: sess)
    app_mod.ledger_append("g2", "bob", 2.0, 40.0)
    assert sess.called is True
    assert "g2" not in app_mod._MEMORY_LEDGER  # did not fall back to memory


def test_ledger_append_sheets_error_falls_back(app_mod, monkeypatch):
    class Sess:
        def post(self, *a, **k):
            raise requests.RequestException("nope")

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    app_mod.ledger_append("g3", "carol", 1.0, 10.0)
    assert app_mod._MEMORY_LEDGER["g3"][0]["member"] == "carol"


def test_ledger_state_memory_empty(app_mod):
    st = app_mod.ledger_state("empty")
    assert st["members"] == [] and st["swaps"] == 0
    assert st["goal_kg"] == 50.0 and st["goal_pct"] == 0
    assert st["backend"] == "memory"


def test_ledger_state_memory_aggregates(app_mod):
    app_mod.ledger_append("fam", "a", 10.0, 100.0)
    app_mod.ledger_append("fam", "b", 20.0, 200.0)
    st = app_mod.ledger_state("fam")
    assert set(st["members"]) == {"a", "b"}
    assert st["total_kg"] == 30.0 and st["total_money_inr"] == 300.0


def test_ledger_state_sheets_success(app_mod, monkeypatch):
    rows = [
        ["team", "alice", "10", "100"],
        ["team", "bob", "45", "200"],
        ["other", "x", "5", "5"],   # different grove -> skipped
        ["team", "short"],          # malformed -> skipped
    ]

    class Sess:
        def get(self, *a, **k):
            return FakeResp({"values": rows})

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    st = app_mod.ledger_state("team")
    assert set(st["members"]) == {"alice", "bob"}
    assert st["total_kg"] == 55.0
    assert st["goal_pct"] == 55  # 55/100
    assert st["backend"] == "sheets"


def test_ledger_state_sheets_goal_capped_at_100(app_mod, monkeypatch):
    class Sess:
        def get(self, *a, **k):
            return FakeResp({"values": [["g", "a", "200", "500"]]})

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    assert app_mod.ledger_state("g")["goal_pct"] == 100


def test_ledger_state_sheets_error_falls_back_to_memory(app_mod, monkeypatch):
    app_mod._MEMORY_LEDGER["g"] = [{"member": "m", "kg": 4.0, "money": 40.0}]

    class Sess:
        def get(self, *a, **k):
            raise requests.RequestException("boom")

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    st = app_mod.ledger_state("g")
    assert st["members"] == ["m"] and st["total_kg"] == 4.0


# ---------------------------------------------------------------------------
# clean_input + _as_float
# ---------------------------------------------------------------------------

def test_clean_input_rejects_non_string(app_mod):
    with pytest.raises(ValueError):
        app_mod.clean_input(123)


def test_clean_input_rejects_empty(app_mod):
    with pytest.raises(ValueError):
        app_mod.clean_input("   ")


def test_clean_input_rejects_too_long(app_mod):
    with pytest.raises(ValueError):
        app_mod.clean_input("x" * (app_mod.MAX_INPUT_CHARS + 1))


def test_clean_input_ok(app_mod):
    assert app_mod.clean_input("  hello  ") == "hello"


def test_as_float(app_mod):
    assert app_mod._as_float("3.5", 0.0) == 3.5
    assert app_mod._as_float(None, 2.0) == 2.0
    assert app_mod._as_float("bad", 1.0) == 1.0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_index_ok_and_cached(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "public, max-age=300"
    assert b"Sprout" in r.data


def test_healthz(client):
    r = client.get("/healthz")
    assert r.get_json()["ok"] is True


def test_api_log_invalid(client):
    r = client.post("/api/log", json={})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_api_log_valid(client):
    r = client.post("/api/log", json={"activity": "drove 20 km, beef burger"})
    body = r.get_json()
    assert r.status_code == 200
    assert "gauge" in body and "equivalence" in body
    assert body["swap"]["tip"]


def test_api_whatif_invalid(client):
    assert client.post("/api/whatif", json={}).status_code == 400


def test_api_whatif_valid(client):
    r = client.post("/api/whatif", json={"change": "bike to work"})
    assert r.status_code == 200
    assert r.get_json()["annual_kg"] == 180.0


def test_api_grove_invalid(client):
    assert client.post("/api/grove", json={}).status_code == 400


def test_api_grove_state(client):
    r = client.post("/api/grove", json={"grove": "g"})
    assert r.status_code == 200
    assert r.get_json()["backend"] == "memory"


def test_api_grove_log_with_member(client, app_mod):
    r = client.post(
        "/api/grove",
        json={"grove": "g", "action": "log", "member": "alice", "kg_saved": 3, "money_inr": 90},
    )
    assert r.get_json()["swaps"] == 1
    assert app_mod._MEMORY_LEDGER["g"][0]["member"] == "alice"


def test_api_grove_log_member_defaults_to_you(client, app_mod):
    client.post("/api/grove", json={"grove": "g", "action": "log"})
    assert app_mod._MEMORY_LEDGER["g"][0]["member"] == "you"


def test_api_grove_log_blank_member_defaults_to_you(client, app_mod):
    client.post("/api/grove", json={"grove": "g", "action": "log", "member": "   "})
    assert app_mod._MEMORY_LEDGER["g"][0]["member"] == "you"


# ---------------------------------------------------------------------------
# gzip middleware
# ---------------------------------------------------------------------------

def test_gzip_compresses_large_html(client):
    r = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") == "gzip"
    assert r.headers.get("Vary") == "Accept-Encoding"


def test_gzip_skipped_without_accept_encoding(client):
    r = client.get("/", headers={"Accept-Encoding": "identity"})
    assert "Content-Encoding" not in r.headers


def test_gzip_skipped_for_small_error_response(client):
    r = client.post("/api/log", json={}, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 400
    assert r.headers.get("Content-Encoding") != "gzip"
