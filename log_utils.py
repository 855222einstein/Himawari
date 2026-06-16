import html
import logging
import platform
from datetime import datetime
from typing import Optional, Union

import aiohttp
from pyrogram import Client

from config import LOG_CHAT_ID, BOT_TOKEN

logger = logging.getLogger(__name__)

_LOG_DISABLED = False

# Set at startup by init_bot_info() — uses real Telegram bot name everywhere
_BOT_NAME: str = "Bot"
_BOT_USERNAME: str = ""


def init_bot_info(first_name: str, username: str) -> None:
    """Call once after app.start() with the live bot identity."""
    global _BOT_NAME, _BOT_USERNAME
    _BOT_NAME = first_name or "Bot"
    _BOT_USERNAME = f"@{username}" if username else ""


def _escape(value) -> str:
    return html.escape(str(value or ""))


def _chat_id() -> Optional[Union[int, str]]:
    return LOG_CHAT_ID or None


async def _bot_api(method: str, payload: dict) -> tuple[bool, str]:
    global _LOG_DISABLED
    if _LOG_DISABLED:
        return False, "log disabled after previous failure"
    if not BOT_TOKEN:
        return False, "BOT_TOKEN missing"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=payload) as resp:
                data = await resp.json(content_type=None)
                if data.get("ok"):
                    return True, "ok"
                desc = data.get("description", str(data))
                lowered = desc.lower()
                if any(x in lowered for x in ["chat not found", "bot was kicked", "not enough rights", "forbidden"]):
                    _LOG_DISABLED = True
                return False, desc
    except Exception as exc:
        return False, str(exc)


async def send_log(client: Client, text: str, *, disable_web_page_preview: bool = True) -> bool:
    chat_id = _chat_id()
    if not chat_id:
        return False
    ok, info = await _bot_api(
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true" if disable_web_page_preview else "false",
        },
    )
    if not ok:
        logger.info("Log send skipped: %s", info)
    return ok


async def send_startup_log(client: Client) -> None:
    """Send startup report to log channel using the bot's live Telegram identity."""
    chat_id = _chat_id()
    if not chat_id:
        logger.info("LOG_CHAT_ID not set — startup log skipped.")
        return

    try:
        pyrogram_version = __import__("pyrogram").__version__
        started_date = datetime.utcnow().strftime("%Y-%m-%d")

        # Convert bot name to small caps for the header
        name_display = _BOT_NAME
        username_display = _BOT_USERNAME or "ɴᴏɴᴇ"

        caption = (
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"{name_display}\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"ꜱᴛᴀᴛᴜꜱ      : ᴏɴʟɪɴᴇ\n"
            f"ʙᴏᴛ         : {name_display}\n"
            f"ᴜꜱᴇʀɴᴀᴍᴇ    : {username_display}\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"ᴘʏᴛʜᴏɴ      : v{platform.python_version()}\n"
            f"ᴘʏʀᴏɢʀᴀᴍ    : v{pyrogram_version}\n"
            f"ᴏꜱ          : {platform.system()} {platform.release()}\n\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            f"ꜱᴛᴀʀᴛᴇᴅ     : {started_date}\n"
            "ᴄᴏʀᴇ        : ᴀᴄᴛɪᴠᴇ\n"
            "ꜱᴛᴀᴛᴇ       : ꜱᴛᴀʙʟᴇ\n\n"
            "━━━━━━━━━━━━━━━━━━"
        )

        ok, info = await _bot_api(
            "sendMessage",
            {
                "chat_id": str(chat_id),
                "text": caption,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )
        if not ok:
            logger.info("Startup log skipped: %s", info)
        else:
            logger.info("Startup log sent to log channel.")

    except Exception as exc:
        logger.info("Startup log skipped: %s", exc)


async def log_command(client: Client, message) -> None:
    """Log commands and private messages to the log channel."""
    if not LOG_CHAT_ID or not message or not message.from_user:
        return

    user = message.from_user
    chat = message.chat
    text = message.text or message.caption or "<non-text message>"

    is_command = isinstance(text, str) and text.startswith("/")
    is_private = bool(chat and chat.type and str(chat.type).endswith("PRIVATE"))
    if not is_command and not is_private:
        return

    log_text = (
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"{_BOT_NAME} ʟᴏɢ\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"ᴜꜱᴇʀ       : {_escape(user.first_name)}\n"
        f"ᴜꜱᴇʀ ɪᴅ    : {user.id}\n\n"
        f"ᴜꜱᴇʀɴᴀᴍᴇ   : @{_escape(user.username) if user.username else 'ɴᴏɴᴇ'}\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"ᴄʜᴀᴛ       : {_escape(chat.title if chat and chat.title else 'ᴘʀɪᴠᴀᴛᴇ')}\n"
        f"ᴄʜᴀᴛ ɪᴅ    : {chat.id if chat else 'ɴ/ᴀ'}\n\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"ᴄᴏᴍᴍᴀɴᴅ    : {_escape(text[:3500])}\n\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await send_log(client, log_text)
