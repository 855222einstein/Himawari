# ============================================================
# Group Manager Bot / NomadeHelpBot
# Pyrogram entrypoint with CipherElite-style startup logger
# ============================================================

import logging

from pyrogram import Client, idle, filters
from pyrogram.types import Message

from config import API_ID, API_HASH, BOT_TOKEN, LOG_CHAT_ID
from security import verify_integrity, get_runtime_key
from handlers import register_all_handlers
from log_utils import send_startup_log, log_command, send_log
from health_server import start_health_server

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
        return await message.reply_text("❌ LOG_CHAT_ID is not set in environment variables.")
    sent = await send_log(client, "<b>✅ NomadeHelpBot log channel test successful.</b>")
    await message.reply_text(
        "✅ Log channel working."
        if sent
        else "❌ Could not send to LOG_CHAT_ID. Add bot to log channel/group as admin and check the ID."
    )


@app.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    await message.reply_text("✅ Bot is alive.")


@app.on_message(group=99)
async def command_logger(client: Client, message: Message):
    await log_command(client, message)


async def boot():
    register_all_handlers(app)
    logger.info("Starting NomadeHelpBot securely...")
    await app.start()
    await send_startup_log(app)
    logger.info("NomadeHelpBot is online.")
    await idle()
    await app.stop()


if __name__ == "__main__":
    start_health_server()
    app.run(boot())
