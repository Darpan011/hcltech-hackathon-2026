"""Notification worker: consumes onboarding events from Kafka and sends SIMULATED
SMS/e-mail (a log line, as the case allows). Run: python -m app.workers.notifier
"""
import json
import logging
import signal

from confluent_kafka import Consumer, KafkaError

from app.settings import settings

logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("onboardiq.notifier")

TEMPLATES = {
    "APPLICATION_SUBMITTED": "We have received your application {application_id}. We will update you shortly.",
    "DECISION_MADE": "Update on application {application_id}: status is now {status}.",
    "RESUBMISSION_REQUESTED": "Please upload new documents for application {application_id} by {due_date}.",
    "CHECKER_DECISION": "Your application {application_id} has been {status}.",
    "ACCOUNT_OPENED": "Welcome! Your account for application {application_id} is open. Account no. {account_no_masked}.",
    "APPLICATION_EXPIRED": "Application {application_id} was closed because documents were not received in time.",
}


def build_message(event: dict) -> str | None:
    """Turn an event into the text we would send; None for unknown event types."""
    template = TEMPLATES.get(event.get("event_type", ""))
    if not template:
        return None
    values = {"application_id": event.get("key", "")} | event.get("payload", {})
    try:
        return template.format(**values)
    except KeyError as missing:
        log.warning("Event %s missing field %s", event.get("event_id"), missing)
        return None


def run() -> None:
    consumer = Consumer({
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "group.id": "onboardiq-notifier",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,             # commit only after the notification is sent
    })
    consumer.subscribe([settings.kafka_topic_notifications])
    seen: set[str] = set()                       # dedupe redeliveries (at-least-once → effectively once)
    running = True

    def _stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("Notifier listening on topic %s", settings.kafka_topic_notifications)

    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.warning("Kafka error: %s", msg.error())
                continue
            try:
                event = json.loads(msg.value())
            except json.JSONDecodeError:
                log.warning("Skipping malformed message at offset %s", msg.offset())
                consumer.commit(msg)
                continue
            if event.get("event_id") not in seen:
                text = build_message(event)
                if text:
                    log.info("NOTIFY applicant of %s: %s", event.get("key"), text)
                seen.add(event.get("event_id"))
            consumer.commit(msg)
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
