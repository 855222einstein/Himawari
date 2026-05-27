# ============================================================
# plugin/service_delete_system/watcher.py
#
# Listens for Telegram service messages (join / leave only)
# and deletes them immediately if enabled for that chat.
#
# Covered message types:
#   ✅ new_chat_members  — user joined OR was added by someone
#   ✅ left_chat_member  — user left OR was removed
#
# Explicitly NOT touched:
#   ✗ Normal text messages
#   ✗ Media (photos, videos, documents, stickers …)
#   ✗ Bot replies / command responses
#   ✗ Any other service message (pinned, title change, etc.)
# ============================================================

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import (
    MessageDeleteForbidden,  # bot lacks delete permission
    MessageIdInvalid,        # message already gone
    ChatAdminRequired,       # bot is not admin
    FloodWait,               # Telegram rate limit
)

from db_service_delete import get_service_delete

logger = logging.getLogger(__name__)


# ── Core delete helper ──────────────────────────────────────

async def _safe_delete(client: Client, chat_id: int, message_id: int) -> None:
    """
    Delete a single message.
    Handles all expected Telegram errors silently so the bot
    never crashes due to a missing message or missing permission.
    """
    try:
        await client.delete_messages(chat_id, message_id)
        logger.debug("ServiceDelete: deleted msg=%s in chat=%s", message_id, chat_id)

    except FloodWait as e:
        # Telegram rate-limited us — log and skip (don't block the event loop)
        logger.warning(
            "ServiceDelete FloodWait %ss — skipping msg=%s chat=%s",
            e.value, message_id, chat_id,
        )

    except (MessageDeleteForbidden, ChatAdminRequired):
        # Bot does not have Delete Messages permission — log once, keep running
        logger.warning(
            "ServiceDelete: no delete permission in chat=%s. "
            "Grant 'Delete Messages' admin right to the bot.",
            chat_id,
        )

    except MessageIdInvalid:
        # Message was already deleted by someone else — harmless, ignore
        pass

    except Exception as exc:
        # Catch-all so the watcher never raises into Pyrogram's dispatcher
        logger.warning(
            "ServiceDelete: unexpected error chat=%s msg=%s: %s",
            chat_id, message_id, exc,
        )


# ── Watcher: new_chat_members ───────────────────────────────

async def on_new_member(client: Client, message: Message) -> None:
    """
    Triggered when one or more users join or are added to the group.
    Deletes the Telegram service message if the feature is enabled.
    """
    # Skip if feature is off for this chat
    if not await get_service_delete(message.chat.id):
        return

    logger.debug(
        "ServiceDelete: new_chat_members in chat=%s msg=%s",
        message.chat.id, message.id,
    )
    await _safe_delete(client, message.chat.id, message.id)


# ── Watcher: left_chat_member ───────────────────────────────

async def on_left_member(client: Client, message: Message) -> None:
    """
    Triggered when a user leaves or is removed from the group.
    Deletes the Telegram service message if the feature is enabled.
    """
    # Skip if feature is off for this chat
    if not await get_service_delete(message.chat.id):
        return

    logger.debug(
        "ServiceDelete: left_chat_member in chat=%s msg=%s",
        message.chat.id, message.id,
    )
    await _safe_delete(client, message.chat.id, message.id)


# ── Registration helper ─────────────────────────────────────

def register_service_delete_watcher(app: Client) -> None:
    """
    Register service-message watchers using Pyrogram's built-in
    filters.new_chat_members and filters.left_chat_member.

    handler group=20 keeps it well separated from other plugins
    (lock_system uses group=1, autodelete scheduler uses group=10).
    """
    # join / user added
    app.on_message(
        filters.new_chat_members & filters.group,
        group=20,
    )(on_new_member)

    # leave / user removed
    app.on_message(
        filters.left_chat_member & filters.group,
        group=20,
    )(on_left_member)

    logger.info("✅ ServiceDelete watcher registered (new_chat_members | left_chat_member).")
