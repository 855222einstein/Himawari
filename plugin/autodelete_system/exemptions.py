# ============================================================
# Auto Delete System — Exemptions
# plugin/autodelete_system/exemptions.py
#
# Messages exempt from auto-delete:
#   1. Currently pinned messages (tracked via pin service events)
#   2. Admin / owner messages (when skip_admins is enabled)
# ============================================================

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus

logger = logging.getLogger(__name__)

# {chat_id: set[message_id]} — pinned message IDs per chat
_pinned_ids: dict[int, set[int]] = {}


def mark_pinned(chat_id: int, message_id: int) -> None:
    _pinned_ids.setdefault(chat_id, set()).add(message_id)


def unmark_pinned(chat_id: int, message_id: int) -> None:
    if chat_id in _pinned_ids:
        _pinned_ids[chat_id].discard(message_id)


async def _on_pin_service(client: Client, message: Message) -> None:
    """
    Fires when Telegram sends a 'pinned_message' service event.
    Stores the pinned message ID so the scheduler can skip it.
    """
    if message.pinned_message:
        mid = message.pinned_message.id
        mark_pinned(message.chat.id, mid)
        logger.debug("📌 Tracked pinned msg=%s in chat=%s", mid, message.chat.id)


async def is_exempt(client: Client, message: Message, cfg: dict) -> bool:
    """
    Returns True if this message must NOT be auto-deleted.

    Checks (in order):
      1. Message is currently pinned in its chat.
      2. Sender is an admin/owner AND skip_admins is enabled.
         Anonymous admins (from_user=None, sender_chat set) are always exempt
         when skip_admins is on.
    """
    chat_id = message.chat.id

    # ── 1. Pinned message check ──────────────────────────────
    if message.id in _pinned_ids.get(chat_id, set()):
        return True

    # ── 2. Skip-admins check ─────────────────────────────────
    if cfg.get("skip_admins"):
        # Anonymous admin → from_user is None, message sent as the group chat
        if message.from_user is None:
            return True
        try:
            member = await client.get_chat_member(chat_id, message.from_user.id)
            if member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
                return True
        except Exception:
            pass

    return False


def register_exemption_watcher(app: Client) -> None:
    """Register the handler that tracks pinned message IDs (group=9, before scheduler)."""
    app.on_message(
        filters.group & filters.pinned_message,
        group=9,
    )(_on_pin_service)
    logger.info("✅ Exemption watcher registered (pinned messages tracked).")
