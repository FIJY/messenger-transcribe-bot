"""Generate a Telethon TELEGRAM_SESSION_STRING for local use."""

from __future__ import annotations

import asyncio
import getpass
import os

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession


async def main() -> None:
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH before running this script.")

    phone = input("Telegram phone number: ").strip()
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    try:
        await client.send_code_request(phone)
        code = input("Telegram code: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = getpass.getpass("Telegram 2FA password: ")
            await client.sign_in(password=password)

        print("TELEGRAM_SESSION_STRING=")
        print(client.session.save())
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
