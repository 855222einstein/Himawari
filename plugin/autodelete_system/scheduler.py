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
#
# Exempt from deletion:
# 🔒 Pinned messages (tracked via pin service events)
# 🛡️ Admin/owner messages (when skip_admins is enabled)
# ============================================================

import asyncio
import random
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
from plugin.autodelete_system.exemptions import is_exempt, register_exemption_watcher

logger = logging.getLogger(__name__)

# Log ChatAdminRequired only once per chat to avoid spam
_admin_warned: set[int] = set()


async def _delete_after(client: Client, chat_id: int, message_id: int, delay: int):
    """Sleep then delete. Handles all Telegram errors per spec."""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
        logger.debug("🗑️ Deleted msg=%s in chat=%s", message_id, chat_id)
    except FloodWait as e:
        jitter = random.uniform(1, 5)
        logger.warning("FloodWait %ss — retrying after %.1fs (chat=%s)", e.value, jitter, chat_id)
        await asyncio.sleep(e.value + jitter)
        try:
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass
    except (MessageDeleteForbidden, MessageIdInvalid):
        pass
    except ChatAdminRequired:
        if chat_id not in _admin_warned:
            _admin_warned.add(chat_id)
            logger.warning(
                "ChatAdminRequired in chat=%s — bot needs 'Delete Messages' permission.", chat_id
            )
    except Exception as exc:
        logger.warning("AutoDelete error chat=%s msg=%s: %s", chat_id, message_id, exc)


async def message_watcher(client: Client, message: Message):
    """
    Runs on every non-service group message (handler group=10).
    Schedules deletion for ALL content types when autodelete is active,
    unless the message is exempt (pinned or sent by an admin with skip_admins on).
    """
    chat_id = message.chat.id
    cfg = await get_autodelete(chat_id)

    if not cfg["enabled"] or cfg["seconds"] <= 0:
        return

    if await is_exempt(client, message, cfg):
        return

    asyncio.create_task(
        _delete_after(client, chat_id, message.id, cfg["seconds"])
    )


def register_autodelete_scheduler(app: Client):
    register_exemption_watcher(app)
    app.on_message(
        filters.group & ~filters.service,
        group=10,
    )(message_watcher)
    logger.info("✅ AutoDelete scheduler registered (all message types, with exemptions).")
