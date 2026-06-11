"""Full-coverage tests for Sprout. All network (NVIDIA, Sheets) is mocked."""
import json

import pytest
import requests

from tests.conftest import FakeResp

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_extract_json_variants(app_mod):
    assert app_mod._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert app_mod._extract_json('here: {"b": 2} done') == {"b": 2}
    with pytest.raises(ValueError):
        app_mod._extract_json("no json here")


def test_find_money(app_mod):
    assert app_mod._find_money("bill is ₹3,200 a month") == 3200.0
    assert app_mod._find_money("no numbers here") == 0.0


def test_first_number(app_mod):
    assert app_mod._first_number("about 150 km away") == 150.0
    assert app_mod._first_number("no digits") is None


# ---------------------------------------------------------------------------
# Offline fallbacks
# ---------------------------------------------------------------------------

def test_offline_savings(app_mod):
    out = app_mod.offline_savings("electricity ₹3,200")
    assert out["monthly_spend_inr"] == 3200.0 and len(out["actions"]) >= 3


def test_offline_trip_with_and_without_distance(app_mod):
    out = app_mod.offline_trip("Mumbai to Pune 150 km")
    assert out["distance_km"] == 150.0 and out["best"] == "Cycle"
    assert app_mod.offline_trip("just somewhere")["distance_km"] == 10.0


def test_offline_claim(app_mod):
    out = app_mod.offline_claim("100% eco-friendly miracle")
    assert out["verdict"] == "mixed" and out["reasons"]


def test_offline_shop(app_mod):
    out = app_mod.offline_shop("2 kg beef, plastic bottles")
    assert out["items"] and out["total_kg"] > 0 and out["total_saves_kg"] > 0


def test_offline_worth(app_mod):
    out = app_mod.offline_worth("rooftop solar")
    assert out["payback_years"] == 5.0 and out["verdict"] == "borderline"


def test_offline_lookup(app_mod):
    out = app_mod.offline_lookup("a flight to Delhi")
    assert out["kg"] == 5.0 and out["equivalent"]


# ---------------------------------------------------------------------------
# Offline classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("is rooftop solar worth it", "worth"),
    ("what's the footprint of my amazon order", "shop"),
    ("is this sustainable collection real", "claim"),
    ("how do I lower my electricity bill", "savings"),
    ("travel from Delhi to Agra by road", "trip"),
    ("footprint of a banana", "lookup"),
])
def test_classify_offline(app_mod, text, expected):
    assert app_mod.classify_offline(text) == expected


# ---------------------------------------------------------------------------
# NVIDIA client + unified analyze
# ---------------------------------------------------------------------------

def test_nvidia_chat_returns_content(app_mod, monkeypatch):
    payload = {"choices": [{"message": {"content": "hi"}}]}
    monkeypatch.setattr(app_mod.requests, "post", lambda *a, **k: FakeResp(payload))
    assert app_mod.nvidia_chat("sys", "user") == "hi"


def test_analyze_offline_no_key_classifies(app_mod):
    env = app_mod.analyze("how do I cut my electricity bill")
    assert env["source"] == "offline" and env["mode"] == "savings"


def test_analyze_offline_no_key_honours_hint(app_mod):
    env = app_mod.analyze("anything", hint="trip")
    assert env["source"] == "offline" and env["mode"] == "trip"


VALID = {
    "savings": {"mode": "savings", "result": {"summary": "s", "monthly_spend_inr": 100,
        "annual_kg": 5, "actions": [{"action": "x", "saves_inr_year": 10, "saves_kg_year": 1,
        "effort": "easy", "payback": "now"}]}},
    "trip": {"mode": "trip", "result": {"from": "A", "to": "B", "distance_km": 10,
        "options": [{"mode": "Train", "kg": 0.4, "cost_inr": 12, "time": "1h", "note": "n"}],
        "best": "Train"}},
    "claim": {"mode": "claim", "result": {"claim": "c", "verdict": "legit", "confidence": 0.8,
        "reasons": ["r"], "tip": "t"}},
    "shop": {"mode": "shop", "result": {"summary": "s", "total_kg": 4,
        "items": [{"item": "i", "kg": 2, "swap": "w", "saves_kg": 1}], "total_saves_kg": 1}},
    "worth": {"mode": "worth", "result": {"item": "x", "upfront_inr": 1, "saves_inr_year": 2,
        "saves_kg_year": 3, "payback_years": 4, "verdict": "worth it", "note": "n"}},
    "lookup": {"mode": "lookup", "result": {"thing": "t", "kg": 2, "unit": "u",
        "equivalent": "e", "context": "c"}},
}


@pytest.mark.parametrize("mode", list(VALID))
def test_analyze_nvidia_success_each_mode(app_mod, monkeypatch, mode):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    monkeypatch.setattr(app_mod, "nvidia_chat", lambda s, u: json.dumps(VALID[mode]))
    env = app_mod.analyze("question")
    assert env["source"] == "nvidia" and env["mode"] == mode


def test_analyze_nvidia_success_with_hint(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    captured = {}

    def fake(system, user):
        captured["user"] = user
        return json.dumps(VALID["savings"])

    monkeypatch.setattr(app_mod, "nvidia_chat", fake)
    env = app_mod.analyze("my bill", hint="savings")
    assert env["mode"] == "savings"
    assert captured["user"].startswith("Preferred mode: savings")


def test_analyze_nvidia_bad_mode_falls_back(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    monkeypatch.setattr(app_mod, "nvidia_chat", lambda s, u: '{"mode": "nonsense", "result": {}}')
    assert app_mod.analyze("x")["source"] == "offline"


def test_analyze_nvidia_missing_required_falls_back(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")
    # Valid mode but result missing the required "actions" key.
    bad = '{"mode": "savings", "result": {"summary": "x"}}'
    monkeypatch.setattr(app_mod, "nvidia_chat", lambda s, u: bad)
    assert app_mod.analyze("bill")["source"] == "offline"


def test_analyze_nvidia_network_error_falls_back(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "NVIDIA_API_KEY", "key")

    def boom(s, u):
        raise requests.RequestException("down")

    monkeypatch.setattr(app_mod, "nvidia_chat", boom)
    assert app_mod.analyze("trip A to B")["source"] == "offline"


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
    app_mod.ledger_append("p1", "LED swap", 60.0, 900.0)
    assert app_mod._MEMORY_LEDGER["p1"][0]["action"] == "LED swap"


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
    app_mod.ledger_append("p2", "AC", 200.0, 3600.0)
    assert sess.called is True and "p2" not in app_mod._MEMORY_LEDGER


def test_ledger_append_sheets_error_falls_back(app_mod, monkeypatch):
    class Sess:
        def post(self, *a, **k):
            raise requests.RequestException("nope")

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    app_mod.ledger_append("p3", "strip", 80.0, 1200.0)
    assert app_mod._MEMORY_LEDGER["p3"][0]["action"] == "strip"


def test_ledger_state_memory_empty(app_mod):
    st = app_mod.ledger_state("none")
    assert st["actions"] == [] and st["count"] == 0
    assert st["total_inr_year"] == 0 and st["backend"] == "memory"


def test_ledger_state_memory_aggregates(app_mod):
    app_mod.ledger_append("home", "AC", 200.0, 3600.0)
    app_mod.ledger_append("home", "LED", 60.0, 900.0)
    st = app_mod.ledger_state("home")
    assert st["count"] == 2 and st["total_inr_year"] == 4500 and st["total_kg_year"] == 260.0


def test_ledger_state_sheets_success(app_mod, monkeypatch):
    rows = [
        ["home", "AC", "200", "3600"],
        ["home", "LED", "60", "900"],
        ["other", "x", "5", "5"],   # different plan -> skipped
        ["home", "bad"],            # malformed -> skipped
    ]

    class Sess:
        def get(self, *a, **k):
            return FakeResp({"values": rows})

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    st = app_mod.ledger_state("home")
    assert st["count"] == 2 and st["total_inr_year"] == 4500 and st["backend"] == "sheets"


def test_ledger_state_sheets_error_falls_back(app_mod, monkeypatch):
    app_mod._MEMORY_LEDGER["home"] = [{"action": "m", "kg": 4.0, "inr": 40.0}]

    class Sess:
        def get(self, *a, **k):
            raise requests.RequestException("boom")

    monkeypatch.setattr(app_mod, "sheets_enabled", lambda: True)
    monkeypatch.setattr(app_mod, "_sheet_session", lambda: Sess())
    st = app_mod.ledger_state("home")
    assert st["actions"] == ["m"] and st["total_kg_year"] == 4.0


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
    assert client.get("/healthz").get_json()["ok"] is True


def test_api_analyze_invalid_input(client):
    assert client.post("/api/analyze", json={"mode": "savings"}).status_code == 400


def test_api_analyze_with_explicit_mode(client):
    r = client.post("/api/analyze", json={"mode": "savings", "input": "bill ₹3200"})
    body = r.get_json()
    assert r.status_code == 200 and body["mode"] == "savings" and body["result"]["actions"]


def test_api_analyze_auto_routes(client):
    r = client.post("/api/analyze", json={"mode": "auto", "input": "how do I lower my electricity bill"})
    body = r.get_json()
    assert r.status_code == 200 and body["mode"] == "savings"


def test_api_plan_invalid(client):
    assert client.post("/api/plan", json={}).status_code == 400


def test_api_plan_state(client):
    r = client.post("/api/plan", json={"plan": "home"})
    assert r.status_code == 200 and r.get_json()["backend"] == "memory"


def test_api_plan_commit_with_label(client, app_mod):
    r = client.post("/api/plan", json={
        "plan": "home", "action": "commit", "label": "LED swap", "kg_year": 60, "inr_year": 900})
    assert r.get_json()["count"] == 1
    assert app_mod._MEMORY_LEDGER["home"][0]["action"] == "LED swap"


def test_api_plan_commit_default_label(client, app_mod):
    client.post("/api/plan", json={"plan": "home", "action": "commit"})
    assert app_mod._MEMORY_LEDGER["home"][0]["action"] == "Saving"


def test_api_plan_commit_blank_label(client, app_mod):
    client.post("/api/plan", json={"plan": "home", "action": "commit", "label": "   "})
    assert app_mod._MEMORY_LEDGER["home"][0]["action"] == "Saving"


# ---------------------------------------------------------------------------
# gzip middleware
# ---------------------------------------------------------------------------

def test_gzip_compresses_large_html(client):
    r = client.get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") == "gzip" and r.headers.get("Vary") == "Accept-Encoding"


def test_gzip_skipped_without_accept_encoding(client):
    r = client.get("/", headers={"Accept-Encoding": "identity"})
    assert "Content-Encoding" not in r.headers


def test_gzip_skipped_for_small_error_response(client):
    r = client.post("/api/analyze", json={}, headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 400 and r.headers.get("Content-Encoding") != "gzip"
