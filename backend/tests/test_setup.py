"""Smoke tests for the starting configuration."""
from fastapi import Query
from fastapi.testclient import TestClient

from app.errors import ApiError
from app.events import EventPublisher
from app.main import app
from app.workers.notifier import build_message


@app.get("/api/v1/_test/error")
def _raise_api_error():
    raise ApiError(409, "CONFLICT", "Case was changed by someone else")


@app.get("/api/v1/_test/validate")
def _validate(age: int = Query(ge=18)):
    return {"age": age}


client = TestClient(app)


def test_health_reports_dependencies():
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["db"] in {"up", "down"}
    assert body["kafka"] == "disabled"


def test_api_error_uses_standard_shape():
    res = client.get("/api/v1/_test/error")
    assert res.status_code == 409
    assert res.json() == {"error": {"code": "CONFLICT", "message": "Case was changed by someone else", "fields": []}}


def test_validation_error_lists_fields():
    res = client.get("/api/v1/_test/validate", params={"age": 12})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["fields"][0]["field"] == "age"


def test_unknown_route_is_404_in_standard_shape():
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_publisher_without_kafka_still_returns_event():
    event = EventPublisher(False, "unused:9092", "t").publish("DECISION_MADE", "A2000001", {"status": "AUTO_APPROVED"})
    assert event["event_type"] == "DECISION_MADE" and event["key"] == "A2000001"


def test_notifier_builds_message_and_ignores_unknown_events():
    msg = build_message({"event_type": "DECISION_MADE", "key": "A2000004", "payload": {"status": "IN_REVIEW"}})
    assert msg == "Update on application A2000004: status is now IN_REVIEW."
    assert build_message({"event_type": "SOMETHING_ELSE"}) is None
