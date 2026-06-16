# ============================================================
# Himawari Help Bot — Pyrogram entrypoint
# Bot name is fetched live from Telegram at startup.
# ============================================================

import logging

from pyrogram import Client, idle, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHAT_ID
from security import verify_integrity, get_runtime_key
from handlers import register_all_handlers
from log_utils import send_startup_log, log_command, send_log, init_bot_info

logging.basicConfig(
    format="[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

verify_integrity()
RUNTIME_KEY = get_runtime_key()

app = Client(
    "group_manager_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)


@app.on_message(filters.command("logtest"))
async def log_test(client: Client, message: Message):
    if not LOG_CHAT_ID:
        return await message.reply_text(
            "❌ **LOG_CHAT_ID not set**\n\n"
            "Add `LOG_CHAT_ID` to your environment secrets.\n"
            "Use the chat's numeric ID (e.g. `-1001234567890`) "
            "or a public username (e.g. `@mychannel`).\n\n"
            "The bot must be an admin/member of that chat."
        )
    sent = await send_log(client, "<b>✅ Log channel test successful.</b>")
    await message.reply_text(
        "✅ Log channel is working."
        if sent
        else "❌ Could not send to log channel. Make sure the bot is added as admin and the ID is correct."
    )


@app.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    await message.reply_text("✅ Bot is alive.")


@app.on_message(group=99)
async def command_logger(client: Client, message: Message):
    await log_command(client, message)


async def boot():
    register_all_handlers(app)
    await app.start()

    # Fetch live bot identity from Telegram — used everywhere instead of hardcoded names
    me = await app.get_me()
    init_bot_info(me.first_name, me.username)
    print(f"✅ {me.first_name} (@{me.username}) is online.")

    await send_startup_log(app)
    await idle()
    await app.stop()


if __name__ == "__main__":
    app.run(boot())
