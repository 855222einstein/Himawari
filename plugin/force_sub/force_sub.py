# ============================================================
# Force Subscribe Plugin
#
# Flow:
#   1. New member joins → welcome message only, no fsub check yet.
#   2. User sends a message → silently check membership in background.
#        - Subscribed to all channels  → message goes through normally.
#        - Not subscribed               → escalation cycle begins.
#
#   Escalation cycle (per user, per chat):
#     Stage 0 → delete message, send fsub notice (+ Join button),
#               notice auto-deletes after 30s, 30s window starts.
#     Stage 1 → ignored notice + sent again within 30s:
#               delete message, send random sticker as a REPLY to the
#               notice, sticker auto-deletes after 10s, fresh 30s window.
#     Stage 2 → ignored sticker + sent again within 30s:
#               delete message, mute user for 30s. Mute auto-lifts and
#               state is cleared. Cycle fully resets after that.
#
#   If the 30s window expires with no further message, the stage timer
#   simply lapses — state is cleared so the next message starts fresh
#   at Stage 0 again.
#
#   Burst protection: an asyncio.Lock per (chat_id, user_id) ensures
#   simultaneous messages (e.g. an album) are processed one at a time,
#   so only a single notice/sticker is ever sent per cycle step.
#
# Commands:
#   /setfsub  LABEL | @channel  LABEL2 | @channel2
#   /clearfsub
#   /setfsubmsg  <text>  (supports {mention} {first_name} {username} {title})
#   /delfsubmsg
#   /viewfsub
# ============================================================

import asyncio
import logging
import random
import re
import time
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    UserNotParticipant,
    ChatAdminRequired,
    ChannelPrivate,
    FloodWait,
    MessageDeleteForbidden,
    MessageIdInvalid,
)
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
)
import db
from plugin.group_guard.group_guard import group_is_approved

logger = logging.getLogger(__name__)

DEFAULT_FSUB_MSG = (
    "Hey {mention} 👋\n\n"
    "You need to join our channel(s) before chatting here.\n\n"
    "Please join all channels below to continue."
)

NOTICE_TTL = 30          # seconds — notice/sticker auto-delete window & stage timeout
STICKER_TTL = 10         # seconds — sticker auto-delete delay
MUTE_SECONDS = 30        # seconds — temporary mute duration

MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

FULL_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_media_messages=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)

# Pre-defined sticker file_ids used at Stage 1. Replace with your own.
_FORCE_SUB_STICKERS_RAW = [
    "CAACAgUAAxkBAAEBp1ZgABXXXXXXXXXXXXXXXXXXXXXXXXXXXAACXXXXXXXXXXXXXXXXX",
    "CAACAgUAAxkBAAEBp1dgABXXXXXXXXXXXXXXXXXXXXXXXXXXXAACXXXXXXXXXXXXXXXXX",
    "CAACAgUAAxkBAAEBp1lgABXXXXXXXXXXXXXXXXXXXXXXXXXXXAACXXXXXXXXXXXXXXXXX",
]

# ── In-memory cycle state ───────────────────────────────────
# key = (chat_id, user_id) -> {
#     "stage": int,            # 0, 1, or 2 (next action to take on their next message)
#     "expires_at": float,     # monotonic time when this stage's window lapses
#     "notice_id": int | None, # message_id of the active fsub notice (Stage 1 replies to it)
# }
_fsub_state: dict[tuple[int, int], dict] = {}

# Per (chat_id, user_id) lock so burst/album messages are handled one at a time.
_fsub_locks: dict[tuple[int, int], asyncio.Lock] = {}


def _get_lock(chat_id: int, user_id: int) -> asyncio.Lock:
    key = (chat_id, user_id)
    lock = _fsub_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _fsub_locks[key] = lock
    return lock


def _get_state(chat_id: int, user_id: int) -> dict | None:
    """Return current state if it exists and hasn't expired, else None (and clear it)."""
    key = (chat_id, user_id)
    state = _fsub_state.get(key)
    if state is None:
        return None
    if time.monotonic() >= state["expires_at"]:
        _fsub_state.pop(key, None)
        return None
    return state


def _set_state(chat_id: int, user_id: int, stage: int, notice_id: int | None):
    _fsub_state[(chat_id, user_id)] = {
        "stage": stage,
        "expires_at": time.monotonic() + NOTICE_TTL,
        "notice_id": notice_id,
    }


def _clear_state(chat_id: int, user_id: int):
    _fsub_state.pop((chat_id, user_id), None)


# ── Helpers ───────────────────────────────────────────────────

def _parse_fsub_args(raw: str):
    channels = []
    errors = []
    pairs = re.split(r'\s{2,}|\n', raw.strip())
    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue
        if "|" not in pair:
            errors.append(f"❌ `{pair}` — format wrong. Use: LABEL | @channel")
            continue
        label, username = pair.split("|", 1)
        label = label.strip()
        username = username.strip()
        if not label:
            errors.append(f"❌ Label empty in: `{pair}`")
            continue
        if not (username.startswith("@") or username.lstrip("-").isdigit()):
            errors.append(f"❌ `{username}` — must be @username or numeric ID")
            continue
        channels.append({"label": label, "username": username})
    return channels, errors


async def _user_subscribed(client, user_id: int, channel: str) -> bool:
    try:
        member = await client.get_chat_member(channel, user_id)
        return member.status not in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT)
    except UserNotParticipant:
        return False
    except (ChatAdminRequired, ChannelPrivate) as e:
        logger.warning("Cannot check %s membership: %s", channel, e)
        return True
    except Exception as e:
        logger.warning("Membership check error %s / %s: %s", channel, user_id, e)
        return True


async def _get_unjoined(client, user_id: int, channels: list) -> list:
    result = []
    for ch in channels:
        if not await _user_subscribed(client, user_id, ch["username"]):
            result.append(ch)
    return result


def _channel_url(username: str) -> str:
    if username.startswith("@"):
        return f"https://t.me/{username.lstrip('@')}"
    clean = str(username).lstrip("-")
    if clean.startswith("100"):
        clean = clean[3:]
    return f"https://t.me/c/{clean}"


def _join_keyboard(channels: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        rows.append([InlineKeyboardButton(
            f"📢 {ch['label']}",
            url=_channel_url(ch["username"])
        )])
    return InlineKeyboardMarkup(rows)


def _format_text(template: str, user, chat_title: str) -> str:
    try:
        return template.format(
            mention=user.mention,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
            username=user.username or user.first_name or "",
            id=user.id,
            title=chat_title or "",
        )
    except Exception:
        return template


async def _safe_delete(client, chat_id: int, message_id: int):
    try:
        await client.delete_messages(chat_id, message_id)
    except FloodWait as e:
        await asyncio.sleep(e.value + random.uniform(1, 3))
        try:
            await client.delete_messages(chat_id, message_id)
        except Exception:
            pass
    except (MessageDeleteForbidden, MessageIdInvalid):
        pass
    except Exception as e:
        logger.warning("Could not delete message %s in %s: %s", message_id, chat_id, e)


async def _delayed_delete(client, chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    await _safe_delete(client, chat_id, message_id)


# ── Registration ──────────────────────────────────────────────

def register_force_sub_plugin(app):

    # ── /setfsub ─────────────────────────────────────────────
    @app.on_message(filters.group & filters.command("setfsub"))
    async def cmd_setfsub(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("❌ Admins only.")

        parts = message.text.split(None, 1)
        if len(parts) < 2:
            return await message.reply_text(
                "**Usage:**\n"
                "`/setfsub LABEL | @channel`\n\n"
                "**Multiple channels:**\n"
                "`/setfsub DISCUSS | @channel1  UPDATE | @channel2`\n\n"
                "_(Separate pairs with 2+ spaces or newlines)_"
            )

        channels, errors = _parse_fsub_args(parts[1])
        if not channels:
            msg = "⚠️ No valid entries.\n\nFormat: `LABEL | @username`"
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors)
            return await message.reply_text(msg)

        await db.set_fsub_channels(message.chat.id, channels)

        lines = ["**ADDED:**"]
        for ch in channels:
            lines.append(f"✅ {ch['label']} → {ch['username']}")
        reply = "\n".join(lines)
        if errors:
            reply += "\n\n⚠️ Skipped:\n" + "\n".join(errors)
        await message.reply_text(reply, disable_web_page_preview=True)

    # ── /clearfsub ───────────────────────────────────────────
    @app.on_message(filters.group & filters.command("clearfsub"))
    async def cmd_clearfsub(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("❌ Admins only.")

        await db.clear_fsub_channels(message.chat.id)
        await message.reply_text("🗑️ **ALL FORCE-SUB CHANNELS CLEARED.**")

    # ── /setfsubmsg ──────────────────────────────────────────
    @app.on_message(filters.group & filters.command("setfsubmsg"))
    async def cmd_setfsubmsg(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("❌ Admins only.")

        parts = message.text.split(None, 1)
        if len(parts) < 2:
            return await message.reply_text(
                "**Usage:**\n"
                "`/setfsubmsg Hey {mention} 👋\\n\\nWelcome!`\n\n"
                "**Placeholders:** `{mention}` `{first_name}` `{username}` `{title}`"
            )

        await db.set_fsub_message(message.chat.id, parts[1])
        preview = parts[1][:300] + ("…" if len(parts[1]) > 300 else "")
        await message.reply_text(
            f"✅ **FORCE-SUB NOTICE MESSAGE SAVED!**\n\n"
            f"{'─' * 16}\n\n{preview}"
        )

    # ── /delfsubmsg ──────────────────────────────────────────
    @app.on_message(filters.group & filters.command("delfsubmsg"))
    async def cmd_delfsubmsg(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("❌ Admins only.")

        await db.clear_fsub_message(message.chat.id)
        await message.reply_text("🗑️ Force-sub notice message cleared. Default will be used.")

    # ── /viewfsub ────────────────────────────────────────────
    @app.on_message(filters.group & filters.command("viewfsub"))
    async def cmd_viewfsub(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("❌ Admins only.")

        channels = await db.get_fsub_channels(message.chat.id)
        fsub_msg = await db.get_fsub_message(message.chat.id)

        if not channels:
            return await message.reply_text(
                "ℹ️ No force-sub channels set.\n"
                "Use `/setfsub LABEL | @channel` to add one."
            )

        lines = ["**Current Force-Sub Channels:**\n"]
        for i, ch in enumerate(channels, 1):
            lines.append(f"{i}. **{ch['label']}** → `{ch['username']}`")

        if fsub_msg:
            lines.append(f"\n**Notice Message:**\n{fsub_msg[:200]}{'…' if len(fsub_msg) > 200 else ''}")
        else:
            lines.append("\n_No custom notice message. Default will be used._")

        await message.reply_text("\n".join(lines), disable_web_page_preview=True)

    # ── New member join — welcome only, no fsub check ─────────
    @app.on_message(filters.group & filters.new_chat_members, group=1)
    async def fsub_new_member(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return

        channels = await db.get_fsub_channels(message.chat.id)
        if not channels:
            return  # force-sub not configured

        me = await client.get_me()
        welcome_text = await db.get_welcome_message(message.chat.id)
        fsub_text = await db.get_fsub_message(message.chat.id) or DEFAULT_FSUB_MSG
        text_template = welcome_text or fsub_text

        for user in message.new_chat_members:
            if user.id == me.id or user.is_bot:
                continue

            # No fsub check on join — just send a plain welcome.
            text = _format_text(text_template, user, message.chat.title)
            try:
                await client.send_message(
                    message.chat.id,
                    text,
                    reply_markup=_join_keyboard(channels),
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.error("Failed to send welcome message: %s", e)

    # ── Message-based escalation cycle ─────────────────────────
    @app.on_message(filters.group & ~filters.service, group=2)
    async def fsub_message_gate(client, message: Message):
        if not message.from_user or message.from_user.is_bot:
            return

        chat_id = message.chat.id
        user_id = message.from_user.id

        if not await group_is_approved(chat_id):
            return

        channels = await db.get_fsub_channels(chat_id)
        if not channels:
            return  # force-sub not configured

        lock = _get_lock(chat_id, user_id)
        async with lock:
            unjoined = await _get_unjoined(client, user_id, channels)

            if not unjoined:
                # Subscribed to everything — clear any stale state, let message through.
                _clear_state(chat_id, user_id)
                return

            state = _get_state(chat_id, user_id)
            stage = state["stage"] if state else 0

            # Always remove the offending message first.
            await _safe_delete(client, chat_id, message.id)

            if stage == 0:
                # Stage 0 — first warning notice
                fsub_text = await db.get_fsub_message(chat_id) or DEFAULT_FSUB_MSG
                notice_text = _format_text(fsub_text, message.from_user, message.chat.title)
                keyboard = _join_keyboard(unjoined)
                try:
                    notice = await client.send_message(
                        chat_id,
                        notice_text,
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                    asyncio.create_task(_delayed_delete(client, chat_id, notice.id, NOTICE_TTL))
                    _set_state(chat_id, user_id, stage=1, notice_id=notice.id)
                except Exception as e:
                    logger.error("Failed to send fsub notice: %s", e)
                    _clear_state(chat_id, user_id)

            elif stage == 1:
                # Stage 1 — sticker warning, replying to the original notice
                sticker_id = random.choice(_FORCE_SUB_STICKERS_RAW)
                notice_id = state.get("notice_id") if state else None
                try:
                    sticker_msg = await client.send_sticker(
                        chat_id,
                        sticker_id,
                        reply_to_message_id=notice_id,
                    )
                    asyncio.create_task(_delayed_delete(client, chat_id, sticker_msg.id, STICKER_TTL))
                    _set_state(chat_id, user_id, stage=2, notice_id=notice_id)
                except Exception as e:
                    logger.error("Failed to send fsub sticker: %s", e)
                    _clear_state(chat_id, user_id)

            else:
                # Stage 2 — temporary mute, then full reset
                try:
                    await client.restrict_chat_member(chat_id, user_id, MUTE_PERMISSIONS)
                except Exception as e:
                    logger.warning("Could not mute user %s in %s: %s", user_id, chat_id, e)

                _clear_state(chat_id, user_id)

                async def _unmute_later():
                    await asyncio.sleep(MUTE_SECONDS)
                    try:
                        await client.restrict_chat_member(chat_id, user_id, FULL_PERMISSIONS)
                    except Exception as e:
                        logger.warning("Could not unmute user %s in %s: %s", user_id, chat_id, e)

                asyncio.create_task(_unmute_later())

        message.stop_propagation()
