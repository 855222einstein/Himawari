# ============================================================
# Group Manager Bot — Auto Delete Scheduler
# plugin/autodelete_system/scheduler.py
#
# Deletes ALL message types after configured delay:
# ✅ Text messages
# ✅ Photos
# ✅ Videos
# ✅ Documents (PDF, ZIP, etc.)
# ✅ Audio / Voice notes
# ✅ Stickers
# ✅ GIFs / Animations
# ✅ Video notes (circles)
# ✅ Polls
# ✅ Location / Venue
# ✅ Forwarded messages
# ============================================================

import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    MessageDeleteForbidden,
    MessageIdInvalid,
    FloodWait,
    ChatAdminRequired,
)

from db_autodelete import get_autodelete

logger = logging.getLogger(__name__)


async def _delete_after(client: Client, chat_id: int, message_id: int, delay: int):
    """Sleep then delete. Handles all Telegram errors gracefully."""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
        logger.debug("🗑️ Deleted msg=%s in chat=%s", message_id, chat_id)
    except FloodWait as e:
        # Rate limited — wait then retry once
        await asyncio.sleep(e.value + 3)
        try:
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass
    except (MessageDeleteForbidden, MessageIdInvalid, ChatAdminRequired):
        # Already deleted or no permission — skip silently
        pass
    except Exception as exc:
        logger.warning("AutoDelete error chat=%s msg=%s: %s", chat_id, message_id, exc)


async def message_watcher(client: Client, message: Message):
    """
    Runs on every non-service group message (handler group=10).
    Schedules deletion for ALL content types when autodelete is active.
    """
    chat_id = message.chat.id
    cfg = await get_autodelete(chat_id)

    if not cfg["enabled"] or cfg["seconds"] <= 0:
        return

    # Schedule deletion — covers every message type Telegram supports
    asyncio.create_task(
        _delete_after(client, chat_id, message.id, cfg["seconds"])
    )


def register_autodelete_scheduler(app: Client):
    app.on_message(
        filters.group & ~filters.service,
        group=10,
    )(message_watcher)
    logger.info("✅ AutoDelete scheduler registered (all message types).")
