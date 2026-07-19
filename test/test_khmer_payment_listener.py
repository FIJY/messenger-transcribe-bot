import asyncio
import datetime
import hmac
from types import SimpleNamespace

import pytest

from services.khmer_payment_listener import (
    ListenerConfig,
    build_payload,
    is_enabled,
    require_config,
    serialize_json_once,
    should_process_event,
    sign_body,
)


def config(chat_id=100, sender_id=200):
    return ListenerConfig(1, "hash", "session", chat_id, sender_id, "https://example.test", "secret")


def complete_env(**overrides):
    env = {
        "TELEGRAM_API_ID": "123",
        "TELEGRAM_API_HASH": "hash",
        "TELEGRAM_SESSION_STRING": "session",
        "TELEGRAM_PAYMENT_CHAT_ID": "100",
        "TELEGRAM_PAYWAY_USER_ID": "200",
        "PAYMENT_INGEST_URL": "https://example.test/api/payments/telegram-ingest",
        "PAYMENT_INGEST_SECRET": "secret",
    }
    env.update(overrides)
    return env


class FakeEvent:
    def __init__(self, chat_id=100, sender_id=200, username="PayWayByABA_bot"):
        self.chat_id = chat_id
        self.sender_id = sender_id
        self.raw_text = "$0.10 paid by BREEGAN SEAN FRANCIS (*138) on Jul 17, 11:18 PM via ABA PAY at SHMYKOVA OLGA. Trx. ID: 178430509212388, APV: 663133."
        self.message = SimpleNamespace(id=321, date=datetime.datetime(2026, 7, 17, 23, 18, tzinfo=datetime.timezone.utc))
        self._sender = SimpleNamespace(username=username)

    async def get_sender(self):
        return self._sender


def test_listener_disabled_by_default():
    assert is_enabled(None) is False
    assert is_enabled("false") is False


def test_require_config_reports_missing_env_when_enabled():
    env = complete_env()
    del env["PAYMENT_INGEST_SECRET"]
    with pytest.raises(RuntimeError, match="PAYMENT_INGEST_SECRET"):
        require_config(env)


def test_hmac_uses_timestamp_dot_exact_raw_body():
    body = serialize_json_once({"raw_text": "Привет", "telegram_message_id": 1})
    signature = sign_body("1780000000", body, "secret")
    expected = hmac.new(b"secret", b"1780000000." + body, "sha256").hexdigest()
    assert signature == expected


def test_changed_body_breaks_signature():
    original = serialize_json_once({"raw_text": "a"})
    changed = serialize_json_once({"raw_text": "b"})
    assert sign_body("1780000000", original, "secret") != sign_body("1780000000", changed, "secret")


def test_wrong_chat_id_ignored():
    assert asyncio.run(should_process_event(FakeEvent(chat_id=999), config())) is False


def test_wrong_sender_id_ignored():
    assert asyncio.run(should_process_event(FakeEvent(sender_id=999), config())) is False


def test_valid_payway_event_processed_and_payload_contains_raw_text():
    event = FakeEvent()
    assert asyncio.run(should_process_event(event, config())) is True
    payload = build_payload(event)
    assert payload["telegram_message_id"] == 321
    assert payload["telegram_chat_id"] == 100
    assert payload["telegram_sender_id"] == 200
    assert payload["raw_text"].startswith("$0.10 paid by")
