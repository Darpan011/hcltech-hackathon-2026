"""Kafka event publisher for NOTIFICATIONS only.

Rules (design.md §23):
- Publish only AFTER the database transaction has committed.
- Never block or fail an API request because Kafka is down: log the event instead.
- No PAN, Aadhaar, DOB or full names in events; consumers look up what they need.
"""
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.settings import settings

log = logging.getLogger("onboardiq.events")
IST = timezone(timedelta(hours=5, minutes=30))

# Event types published by the backend
APPLICATION_SUBMITTED = "APPLICATION_SUBMITTED"
DECISION_MADE = "DECISION_MADE"                     # AUTO_APPROVED / IN_REVIEW / PENDING_CHECKER / AUTO_REJECTED
RESUBMISSION_REQUESTED = "RESUBMISSION_REQUESTED"
CHECKER_DECISION = "CHECKER_DECISION"               # APPROVED / REJECTED / sent back
ACCOUNT_OPENED = "ACCOUNT_OPENED"
APPLICATION_EXPIRED = "APPLICATION_EXPIRED"


def _on_delivery(err, msg) -> None:
    if err is not None:
        log.warning("Kafka delivery failed (%s); event: %s", err, msg.value().decode(errors="replace"))


class EventPublisher:
    """Thin wrapper around a Kafka producer with a log-only fallback."""

    def __init__(self, enabled: bool, bootstrap_servers: str, topic: str):
        self.topic = topic
        self._producer = None
        if enabled:
            from confluent_kafka import Producer  # imported lazily so tests run without Kafka

            self._producer = Producer({
                "bootstrap.servers": bootstrap_servers,
                "client.id": "onboardiq-backend",
                "enable.idempotence": True,      # no duplicates from producer retries
                "acks": "all",
                "message.timeout.ms": 10000,
            })

    @property
    def enabled(self) -> bool:
        return self._producer is not None

    def publish(self, event_type: str, key: str, payload: dict) -> dict:
        """Send one event keyed by application_id (same key → same partition → ordered)."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "occurred_at": datetime.now(IST).isoformat(timespec="seconds"),
            "key": key,
            "payload": payload,
        }
        if not self._producer:
            log.info("EVENT (kafka disabled) %s", json.dumps(event))
            return event
        try:
            self._producer.produce(
                self.topic, key=key.encode(), value=json.dumps(event).encode(), on_delivery=_on_delivery
            )
            self._producer.poll(0)               # serve delivery callbacks, never blocks
        except Exception as exc:                 # BufferError, KafkaException
            log.warning("Kafka publish failed (%s); event: %s", exc, json.dumps(event))
        return event

    def flush(self, timeout: float = 5.0) -> None:
        if self._producer:
            self._producer.flush(timeout)


publisher = EventPublisher(
    settings.kafka_enabled, settings.kafka_bootstrap_servers, settings.kafka_topic_notifications
)


# ---- "publish only after commit" -------------------------------------------------------
# Business code queues events on the DB session; they are sent only if the transaction
# commits, and dropped if it rolls back. So we never notify about a change that didn't happen.

def queue_event(db: Session, event_type: str, application_id: str, payload: dict | None = None) -> None:
    db.info.setdefault("pending_events", []).append((event_type, application_id, payload or {}))


@event.listens_for(Session, "after_commit")
def _publish_after_commit(session: Session) -> None:
    pending = session.info.pop("pending_events", [])
    if session.info.get("suppress_events"):
        return
    for event_type, key, payload in pending:
        publisher.publish(event_type, key, payload)


@event.listens_for(Session, "after_rollback")
def _discard_on_rollback(session: Session) -> None:
    session.info.pop("pending_events", None)
