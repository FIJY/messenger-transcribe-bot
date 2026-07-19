"""Print safe Telegram identifiers from the next incoming message."""

from __future__ import annotations

import asyncio
import os

from telethon import TelegramClient, events
from telethon.sessions import StringSession


async def main() -> None:
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    session_string = os.getenv("TELEGRAM_SESSION_STRING")
    if not api_id or not api_hash or not session_string:
        raise SystemExit("Set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_SESSION_STRING before running this script.")

    client = TelegramClient(StringSession(session_string), int(api_id), api_hash)
    done = asyncio.Event()

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        sender = await event.get_sender()
        chat = await event.get_chat()
        print(f"chat_id={event.chat_id}")
        print(f"sender_id={event.sender_id}")
        print(f"sender_username={getattr(sender, 'username', None)}")
        print(f"chat_title={getattr(chat, 'title', None)}")
        done.set()

    await client.start()
    print("Waiting for one incoming Telegram message...")
    await done.wait()
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
