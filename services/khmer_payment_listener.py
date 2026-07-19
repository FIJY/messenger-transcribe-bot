"""Khmer Mastery Telegram payment listener.

Listens for PayWay Telegram alerts from a configured user/chat and forwards
only the raw Telegram metadata/body to the trusted ingest endpoint.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

LOGGER = logging.getLogger("khmer-payment-listener")
EXPECTED_PAYWAY_USERNAME = "PayWayByABA_bot"
PAYWAY_ALERT_RE = re.compile(
    r"^\$\d+(?:\.\d{1,2})? paid by .+? \(\*\d+\) on .+? via ABA PAY .+? Trx\. ID: .+?, APV: .+?\.?$",
    re.IGNORECASE | re.DOTALL,
)
REQUIRED_ENV = (
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELEGRAM_SESSION_STRING",
    "TELEGRAM_PAYMENT_CHAT_ID",
    "TELEGRAM_PAYWAY_USER_ID",
    "PAYMENT_INGEST_URL",
    "PAYMENT_INGEST_SECRET",
)


@dataclass(frozen=True)
class ListenerConfig:
    api_id: int
    api_hash: str
    session_string: str
    payment_chat_id: int
    payway_user_id: int
    ingest_url: str
    ingest_secret: str


def is_enabled(value: str | None = None) -> bool:
    """Return True only for an explicit, case-insensitive 'true'."""
    raw_value = os.getenv("KHMER_PAYMENT_LISTENER_ENABLED") if value is None else value
    return (raw_value or "").strip().lower() == "true"


def require_config(env: dict[str, str] | None = None) -> ListenerConfig:
    source = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not source.get(name)]
    if missing:
        raise RuntimeError(
            "Khmer payment listener enabled but required environment variables are missing: "
            + ", ".join(missing)
        )

    try:
        api_id = int(source["TELEGRAM_API_ID"])
        payment_chat_id = int(source["TELEGRAM_PAYMENT_CHAT_ID"])
        payway_user_id = int(source["TELEGRAM_PAYWAY_USER_ID"])
    except ValueError as exc:
        raise RuntimeError(
            "Khmer payment listener enabled but TELEGRAM_API_ID, "
            "TELEGRAM_PAYMENT_CHAT_ID, and TELEGRAM_PAYWAY_USER_ID must be integers"
        ) from exc

    return ListenerConfig(
        api_id=api_id,
        api_hash=source["TELEGRAM_API_HASH"],
        session_string=source["TELEGRAM_SESSION_STRING"],
        payment_chat_id=payment_chat_id,
        payway_user_id=payway_user_id,
        ingest_url=source["PAYMENT_INGEST_URL"],
        ingest_secret=source["PAYMENT_INGEST_SECRET"],
    )


def serialize_json_once(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sign_body(timestamp: str, raw_body: bytes, secret: str) -> str:
    signed_payload = timestamp.encode("utf-8") + b"." + raw_body
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def is_payway_alert(text: str | None) -> bool:
    if not text:
        return False
    normalized_text = " ".join(text.strip().split())
    return bool(PAYWAY_ALERT_RE.search(normalized_text))


def sender_username_matches(sender: Any) -> bool:
    username = getattr(sender, "username", None)
    return username is None or username.lower() == EXPECTED_PAYWAY_USERNAME.lower()


async def should_process_event(event: Any, config: ListenerConfig) -> bool:
    if getattr(event, "chat_id", None) != config.payment_chat_id:
        return False
    if getattr(event, "sender_id", None) != config.payway_user_id:
        return False
    sender = await event.get_sender()
    if not sender_username_matches(sender):
        return False
    return is_payway_alert(getattr(event, "raw_text", None))


def build_payload(event: Any) -> dict[str, Any]:
    message_date = getattr(event.message, "date", None)
    return {
        "telegram_message_id": event.message.id,
        "telegram_chat_id": event.chat_id,
        "telegram_sender_id": event.sender_id,
        "message_date": message_date.isoformat() if message_date else None,
        "raw_text": event.raw_text,
    }


async def post_ingest(payload: dict[str, Any], config: ListenerConfig) -> None:
    raw_body = serialize_json_once(payload)
    timestamp = str(int(time.time()))
    signature = sign_body(timestamp, raw_body, config.ingest_secret)
    headers = {
        "X-KM-Ingest-Timestamp": timestamp,
        "X-KM-Ingest-Signature": signature,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(config.ingest_url, content=raw_body, headers=headers)
        response.raise_for_status()
    LOGGER.info("[khmer-payment-listener] payment alert ingested")


async def run_listener(config: ListenerConfig) -> None:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(config.session_string), config.api_id, config.api_hash)

    @client.on(events.NewMessage(chats=config.payment_chat_id, incoming=True))
    async def handle_payment_alert(event: Any) -> None:
        if not await should_process_event(event, config):
            return
        try:
            await post_ingest(build_payload(event), config)
        except Exception as exc:
            LOGGER.warning("[khmer-payment-listener] ingest failed: %s", exc.__class__.__name__)

    while True:
        try:
            LOGGER.info("[khmer-payment-listener] starting Telegram listener")
            await client.start()
            await client.run_until_disconnected()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning("[khmer-payment-listener] listener error; reconnecting: %s", exc.__class__.__name__)
            await asyncio.sleep(5)
        finally:
            if client.is_connected():
                await client.disconnect()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    if not is_enabled():
        LOGGER.info("[khmer-payment-listener] disabled by KHMER_PAYMENT_LISTENER_ENABLED")
        return
    asyncio.run(run_listener(require_config()))


if __name__ == "__main__":
    main()
