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
#     Stage 0 → delete message, send fsub notice (+ Join buttons),
#               notice auto-deletes after 30s, 30s window starts.
#     Stage 1 → ignored notice + sent again within 30s:
#               delete message, send random sticker as a REPLY to the
#               notice (falls back to plain send if notice was deleted),
#               sticker auto-deletes after 10s, fresh 30s window.
#     Stage 2 → ignored sticker + sent again within 30s:
#               delete message, mute user for 30s.
#               State is fully cleared immediately — cycle resets.
#
#   If the 30s window expires with no further message, state lapses
#   automatically — the next message starts fresh at Stage 0.
#
#   Burst protection: an asyncio.Lock per (chat_id, user_id) ensures
#   simultaneous messages (e.g. an album) are processed one at a time,
#   so only a single notice/sticker is ever sent per cycle step.
#
# Commands:
#   /setfsub   LABEL | @channel  LABEL2 | @channel2
#   /clearfsub
#   /checkfsub  — diagnostic: tests bot's ability to verify each channel
#   /setfsubmsg <text>  (supports {mention} {first_name} {username} {title})
#   /delfsubmsg
#   /viewfsub
#
# IMPORTANT SETUP REQUIREMENT:
#   The bot must be an ADMIN in every channel listed in /setfsub.
#   Without admin rights the bot cannot check user membership and
#   force-sub will not work for that channel.
# ============================================================

import asyncio
import logging
import random
import re
import time
from datetime import datetime, timezone, timedelta
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
from . import db
from plugin.group_guard.group_guard import group_is_approved

logger = logging.getLogger(__name__)

DEFAULT_FSUB_MSG = (
    "Hey {mention}\n\n"
    "You need to join our channel(s) before chatting here.\n\n"
    "Please join all channels below to continue."
)

NOTICE_TTL = 30          # seconds — notice/sticker auto-delete window & stage timeout
STICKER_TTL = 10         # seconds — sticker auto-delete delay
ADMIN_WARN_COOLDOWN = 1800  # seconds — how often to remind admin about broken channels

# Escalating mute durations per Stage-3 hit.
# None = permanent restriction (user can no longer send messages in this group).
ESCALATION_DURATIONS: list[int | None] = [
    30,          # 1st hit — 30 seconds
    30,          # 2nd hit — 30 seconds
    None,        # 3rd+ hit — permanent restriction
]

# Tracks last time admin was warned per chat: {chat_id: timestamp}
_ADMIN_WARN_LAST: dict[int, float] = {}

MUTE_PERMISSIONS = ChatPermissions(
    can_send_messages=False,
    can_send_media_messages=False,
    can_send_other_messages=False,
    can_add_web_page_previews=False,
)

# Pre-defined sticker file_ids used at Stage 1.
_FORCE_SUB_STICKERS_RAW = [
    "CAACAgUAAxkBAAMKail5j184VypN5uOha5rRg2dJPxsAAm0VAAI-GflVgXogIGmIUZoeBA",
    "CAACAgUAAxkBAAMMail7NYTQGA50wProtTQQkVm3RzIAAuAcAAKgInhWJuNkodC0RckeBA",
    "CAACAgUAAxkBAAMOail7P_W4-9GUQUBh8MKYIodaw9oAAnkUAALujklVOHjXNcpSGEoeBA",
    "CAACAgUAAxkBAAMQail7b5hyrRIo3_8yxVRvV2IvxC4AAqIWAAJ68olW1fjwcYyIpekeBA",
    "CAACAgUAAxkBAAMSail7e3naQMRCkSqP_q4tFu0PcucAAisMAAKbQ_BUYlO7yJ5mCMEeBA",
    "CAACAgUAAxkBAAMUail7fd3XM1tf1dp5g96c-2SCxWAAAkYQAAKJiPlU6f0rnJ6P0yceBA",
    "CAACAgUAAxkBAAMYail7hg9RHEtZkctsaz5eoYdXJ-AAAnsOAAIuCwFVim60eOoCzDseBA",
    "CAACAgUAAxkBAAMaail7lD4MARmj9OU00cYrldtx6L4AAikVAAJYKslVNIXBL7NC7p0eBA",
    "CAACAgQAAxkBAAMcail7n1YYksUjYan3ESPMLWJu7YQAAmgVAAJmU7FT66oEPHt1-FMeBA",
    "CAACAgQAAxkBAAMeail7oWhk6t7q7chFOye3hJhr1dwAAuUaAAK5BkFR5LS7HeEeAAH_HgQ",
    "CAACAgQAAxkBAAMgail7opXWusM8I6e1ERhAFyN9zGMAArwPAAIl-EBRCWIoGs7F3ugeBA",
    "CAACAgQAAxkBAAMiail7oyzFxiKvKWsgm3jayDzc2b0AAtwPAAIFzLhTY3hSxh26_5oeBA",
    "CAACAgQAAxkBAAMkail7o7vAOJT-oQtLXhzg8e5mVL0AAowPAAI-ewABUNoyQziVBA8sHgQ",
    "CAACAgQAAxkBAAMmail7pWEpp3JTsgojkUbPkFQ_qOMAAssVAAKu7ilTDHwqZT5wLcQeBA",
    "CAACAgQAAxkBAAMoail7pv7HmAQh61BDYaQoOvtRGowAAjgPAAJ113hQ2gPCMIFDCREeBA",
    "CAACAgQAAxkBAAMqail7qM4AATvYvou7Y7riomfXdQABXgACGhEAAujCcFDHVO-cIWfv3x4E",
    "CAACAgQAAxkBAAMsail7qeGLjbRsS8eiadJ28DV2ZKoAAqUNAAIKskFSaiuEZPmFuSseBA",
    "CAACAgQAAxkBAAMuail7qgO0Ps9ZuklDFof-Y8Shh7wAAg0UAAK87nlQEc4LvX3OTfoeBA",
    "CAACAgQAAxkBAAMwail7rcVdH02-qfRqW8qVDCBdtaQAAo4PAAJnGWhQJBPPbFiEOEIeBA",
    "CAACAgQAAxkBAAMyail7rhkWDsxd5wEP-aUEsAFEVekAAu4OAAKcX1hSX0DJLZWx9M4eBA",
    "CAACAgQAAxkBAAM0ail7r7Ckb7Sx4oVAi7Me6ElXjN0AAtMWAAJ4gPBRQJdDlFUEjj8eBA",
    "CAACAgQAAxkBAAM2ail7sBoq7L1TcvGr9rXLysIVgJMAAp8VAAIo41hQXxgectU3fdoeBA",
    "CAACAgQAAxkBAAM4ail7sbJRexmEhBhqiG2CTbJICHcAAngUAAIbzllQrMIOmAlyPN8eBA",
    "CAACAgQAAxkBAAM6ail7s77OzajeblA_abdzlaIkoOwAAq4RAAJ8CvFQZv7xhrhDDrUeBA",
    "CAACAgQAAxkBAAM8ail7tH3AvwxYfcQVU9TPYQM6iBgAAqkYAAKgrFFSq6xrbz5QK2seBA",
    "CAACAgQAAxkBAAM-ail7tVp3UVCAEONfIO0BnC9_F6sAAjIbAALpeBhShPjGWqux7wQeBA",
    "CAACAgQAAxkBAANAail7t6BDeUmR7_VAuUvRiVEO8QEAAtIdAALP3ZhRz6l8TY7EK-QeBA",
    "CAACAgQAAxkBAANCail7uOMXXIyc-8LiMPpuid79wegAAuoRAAImR3BQe4NoAtilxMUeBA",
    "CAACAgQAAxkBAANEail7uuThWyWL-kKPqAAC3GSoauMAAhYWAAIYexFT1RXZqaqBOsMeBA",
    "CAACAgQAAxkBAANGail7v1k1_EFd6aOyGV_fh9wdnTkAAh0VAALVIihTuWparDU7dnceBA",
    "CAACAgQAAxkBAANIail7xcfNZe_-GIgpGhWUEsxHZcYAAk0UAALQBgABU7vo8pNFFc8OHgQ",
    "CAACAgUAAxkBAANKail76V9bDP577BmyVWhuDxN3K-EAAp8TAAKQlulXo4PLxIKpqSceBA",
    "CAACAgUAAxkBAANMail76kGZZz2KlH7N32zlzg8XyyEAAhgSAAKYzehXXgs42Su-oLceBA",
    "CAACAgUAAxkBAANOail7646aSehFDdkS3-DA6uNXOt4AAnoVAAK-5OlXnDljvB-x2jkeBA",
    "CAACAgUAAxkBAANQail761sSgH1lIDAw0gplPodagT8AAmETAAI_IuhXruhPpRhDlI4eBA",
    "CAACAgUAAxkBAANSail77dFeBhzR0O_V42UvDq5IZdEAAlgRAAKAzelXnHKbu_Qdl1UeBA",
    "CAACAgUAAxkBAANUail77ihu7l6_L-liXDSUO0-cxpEAAkYXAAKEA-hXI05rQU313IEeBA",
    "CAACAgUAAxkBAANWail78SwT04iaNhWp9U_1drJ6YrkAAgwVAAKkiQFUl5GASU-h2FweBA",
    "CAACAgUAAxkBAANYail78WO0kXpEau6zFKHrTuqXgKQAAgcRAAKhVPlXvLBiKaxnDiAeBA",
    "CAACAgUAAxkBAANaail78no8kyjowMYny7zuVOl93EIAAj8SAAJ0ifFXRDBduvA5FW4eBA",
    "CAACAgUAAxkBAANcail783pbhfJhtZTYvRZm1gXG5RQAAiwSAAJ5H_lXHIyIyE1OgYoeBA",
    "CAACAgUAAxkBAANeail79w8zAdHG_8YPurZwk61FqqEAAsMaAAJdJQFUiNgX1groxOkeBA",
    "CAACAgUAAxkBAANgail794QBlEYHNVhuMW4f1oqvdsgAAi4TAAKRnvhXHtdjvR6AHH4eBA",
    "CAACAgUAAxkBAANiail7-GQK1FadHHnQztxsfOY_qsoAAosTAALP6QABVOCRqV1xgOFtHgQ",
    "CAACAgUAAxkBAANkail7-McyKPcw8OEzpFSUNM0WQo0AAiwSAAJ5H_lXHIyIyE1OgYoeBA",
    "CAACAgUAAxkBAANlail7-F8Ol8THSrODg_ItU5jHXucAApESAAIKrAFUQAABOpLHISMrHgQ",
    "CAACAgUAAxkBAANoail7-8XEhfhX7euJrBYU4-_ksZEAAk8UAAItcwABVJBjdyuq_9h2HgQ",
    "CAACAgUAAxkBAANpail7-22Rim0XZZ3-BbPCT4Yv21EAAtoSAALTI_hXKhRrcezWL7seBA",
    "CAACAgUAAxkBAANuail7_EA0HBi2ohwNM8Y7J2pjwhgAAkUTAAI2IfhXxwmUebW7ddseBA",
    "CAACAgUAAxkBAANwail7_MZJV52BWqAzQgf3XhCW1OcAAqMRAALmPPhXsYikvAmaVbAeBA",
    "CAACAgUAAxkBAANyail8E6r27hvKtJnk0bRrsLEbLDUAAkMUAAKnuzBW4o_27asInE0eBA",
    "CAACAgUAAxkBAAN0ail8FNnx0WiTtgzlfh4-bWNP2D0AAnQSAAJrAeBVHig_EkL5RhkeBA",
    "CAACAgUAAxkBAAN2ail8Fk39S0capghoPKyHCvQEkZoAAp0fAALAt4FX5uzHYk3LMFEeBA",
    "CAACAgUAAxkBAAN4ail8GMH0LDtCfBmzO3lOmfZeJ4IAAt0aAAIDoflXLrTQilwOknYeBA",
    "CAACAgUAAxkBAAN6ail8KEUEUCRGuoMz2qmjIIsVYLMAAxUAAvSAyVUQUJcUBdRt1x4E",
    "CAACAgUAAxkBAAN8ail8KVX5COMKfX0rXbZYxY3G0wMAAr0YAAICgchVDuZMHaNfrsYeBA",
    "CAACAgUAAxkBAAN-ail8LAt2lrgwnDhN-OSAsF7WkSgAArMVAAJf2MlVbJAGFCf0agQeBA",
    "CAACAgUAAxkBAAOAail8MfYECAV2kvTMmIQeZ_pFIAAkMWAAIIG8hVDYEGCypgBigeBA",
    "CAACAgUAAxkBAAOCail8M97GSBr2YC_ScaLNrsXNLx4AArMWAAK5MvBXOHRY-wx9LWoeBA",
]

# ── In-memory cycle state ───────────────────────────────────
# key = (chat_id, user_id) -> {
#     "stage": int,            # 0=notice sent, 1=sticker sent, 2=mute pending
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


def _set_state(chat_id: int, user_id: int, stage: int, notice_id: int | None, ttl: int = NOTICE_TTL):
    _fsub_state[(chat_id, user_id)] = {
        "stage": stage,
        "expires_at": time.monotonic() + ttl,
        "notice_id": notice_id,
    }


def _clear_state(chat_id: int, user_id: int):
    _fsub_state.pop((chat_id, user_id), None)


# ── Helpers ───────────────────────────────────────────────────

def _parse_fsub_args(raw: str):
    channels = []
    errors = []
    seen_usernames: set[str] = set()
    pairs = re.split(r'\s{2,}|\n', raw.strip())
    for pair in pairs:
        pair = pair.strip()
        if not pair:
            continue
        if "|" not in pair:
            errors.append(f"Format wrong: `{pair}` — Use: LABEL | @channel")
            continue
        label, username = pair.split("|", 1)
        label = label.strip()
        username = username.strip()
        if not label:
            errors.append(f"Label empty in: `{pair}`")
            continue
        if not (username.startswith("@") or username.lstrip("-").isdigit()):
            errors.append(f"`{username}` — must be @username or numeric ID")
            continue
        if username.lower() in seen_usernames:
            errors.append(f"Duplicate skipped: `{username}`")
            continue
        seen_usernames.add(username.lower())
        channels.append({"label": label, "username": username})
    return channels, errors


async def _user_subscribed(client, user_id: int, channel: str) -> tuple[bool, bool]:
    """
    Returns (is_subscribed, is_accessible).
    is_subscribed: True if user is in the channel.
    is_accessible: False if the bot lacks admin rights to check membership.
    When is_accessible is False, is_subscribed is meaningless — caller should warn admin.
    """
    try:
        member = await client.get_chat_member(channel, user_id)
        return member.status not in (ChatMemberStatus.BANNED, ChatMemberStatus.LEFT), True
    except UserNotParticipant:
        return False, True
    except (ChatAdminRequired, ChannelPrivate) as e:
        logger.warning("Cannot check %s membership (bot not admin): %s", channel, e)
        return True, False  # accessible=False signals the caller to warn admin
    except Exception as e:
        logger.warning("Membership check error %s / %s — treating as NOT joined: %s", channel, user_id, e)
        return False, True


async def _check_bot_access(client, bot_id: int, channel: str) -> bool:
    """Returns True if the bot can check membership in this channel (i.e. is an admin)."""
    try:
        member = await client.get_chat_member(channel, bot_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except (ChatAdminRequired, ChannelPrivate):
        return False
    except Exception:
        return False


async def _get_unjoined(client, user_id: int, channels: list) -> tuple[list, list]:
    """
    Returns (unjoined, inaccessible).
    unjoined     — channels the user has definitely NOT joined.
    inaccessible — channels the bot cannot check (not admin there).
    """
    unjoined = []
    inaccessible = []
    seen: set[str] = set()
    for ch in channels:
        key = ch["username"].lower()
        if key in seen:
            continue
        seen.add(key)
        subscribed, accessible = await _user_subscribed(client, user_id, ch["username"])
        if not accessible:
            inaccessible.append(ch)
        elif not subscribed:
            unjoined.append(ch)
    return unjoined, inaccessible


def _channel_url(username: str) -> str:
    if username.startswith("@"):
        return f"https://t.me/{username.lstrip('@')}"
    clean = str(username).lstrip("-")
    if clean.startswith("100"):
        clean = clean[3:]
    return f"https://t.me/c/{clean}"


def _join_keyboard(channels: list) -> InlineKeyboardMarkup:
    """Build the join keyboard. Button text is the admin-set label."""
    rows = []
    seen: set[str] = set()
    for ch in channels:
        key = ch["username"].lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append([InlineKeyboardButton(
            ch["label"],
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
            return await message.reply_text("Admins only.")

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
            msg = "No valid entries.\n\nFormat: `LABEL | @username`"
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors)
            return await message.reply_text(msg)

        await db.set_fsub_channels(message.chat.id, channels)

        lines = ["**ADDED:**"]
        for ch in channels:
            lines.append(f"{ch['label']} -> {ch['username']}")
        reply = "\n".join(lines)
        if errors:
            reply += "\n\nSkipped:\n" + "\n".join(errors)
        await message.reply_text(reply, disable_web_page_preview=True)

        # Immediately validate bot can access every channel and warn if not.
        me = await client.get_me()
        warn_lines = []
        for ch in channels:
            ok = await _check_bot_access(client, me.id, ch["username"])
            if not ok:
                warn_lines.append(ch["username"])
        if warn_lines:
            await message.reply_text(
                "⚠️ **Bot is NOT admin in these channels:**\n"
                + "\n".join(warn_lines) + "\n\n"
                "Force-sub **will not work** for those channels until you add "
                "the bot as admin there.\n\n"
                "**Steps:** Open the channel → Edit → Administrators → Add Admin → select bot.",
                disable_web_page_preview=True,
            )

    # ── /clearfsub ───────────────────────────────────────────
    @app.on_message(filters.group & filters.command("clearfsub"))
    async def cmd_clearfsub(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Admins only.")

        await db.clear_fsub_channels(message.chat.id)
        await message.reply_text("**ALL FORCE-SUB CHANNELS CLEARED.**")

    # ── /setfsubmsg ──────────────────────────────────────────
    @app.on_message(filters.group & filters.command("setfsubmsg"))
    async def cmd_setfsubmsg(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Admins only.")

        parts = message.text.split(None, 1)
        if len(parts) < 2:
            return await message.reply_text(
                "**Usage:**\n"
                "`/setfsubmsg Hey {mention}\\n\\nWelcome!`\n\n"
                "**Placeholders:** `{mention}` `{first_name}` `{username}` `{title}`"
            )

        await db.set_fsub_message(message.chat.id, parts[1])
        preview = parts[1][:300] + ("..." if len(parts[1]) > 300 else "")
        await message.reply_text(
            f"**FORCE-SUB NOTICE MESSAGE SAVED!**\n\n"
            f"{'─' * 16}\n\n{preview}"
        )

    # ── /delfsubmsg ──────────────────────────────────────────
    @app.on_message(filters.group & filters.command("delfsubmsg"))
    async def cmd_delfsubmsg(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Admins only.")

        await db.clear_fsub_message(message.chat.id)
        await message.reply_text("Force-sub notice message cleared. Default will be used.")

    # ── /viewfsub ────────────────────────────────────────────
    @app.on_message(filters.group & filters.command("viewfsub"))
    async def cmd_viewfsub(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Admins only.")

        channels = await db.get_fsub_channels(message.chat.id)
        fsub_msg = await db.get_fsub_message(message.chat.id)

        if not channels:
            return await message.reply_text(
                "No force-sub channels set.\n"
                "Use `/setfsub LABEL | @channel` to add one."
            )

        me = await client.get_me()
        lines = ["**Current Force-Sub Channels:**\n"]
        has_issue = False
        for i, ch in enumerate(channels, 1):
            ok = await _check_bot_access(client, me.id, ch["username"])
            icon = "✅" if ok else "⚠️"
            if not ok:
                has_issue = True
            lines.append(f"{i}. {icon} **{ch['label']}** -> `{ch['username']}`")

        if has_issue:
            lines.append(
                "\n⚠️ Channels marked with ⚠️ will be skipped — "
                "add the bot as admin there to enable force-sub for them.\n"
                "Use `/checkfsub` for a detailed status check."
            )

        if fsub_msg:
            lines.append(f"\n**Notice Message:**\n{fsub_msg[:200]}{'...' if len(fsub_msg) > 200 else ''}")
        else:
            lines.append("\n_No custom notice message. Default will be used._")

        await message.reply_text("\n".join(lines), disable_web_page_preview=True)

    # ── /checkfsub ───────────────────────────────────────────
    @app.on_message(filters.group & filters.command("checkfsub"))
    async def cmd_checkfsub(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return
        member = await client.get_chat_member(message.chat.id, message.from_user.id)
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Admins only.")

        channels = await db.get_fsub_channels(message.chat.id)
        if not channels:
            return await message.reply_text(
                "No force-sub channels configured.\n"
                "Use `/setfsub LABEL | @channel` to add channels."
            )

        me = await client.get_me()
        lines = ["**Force-Sub Channel Diagnostic:**\n"]
        all_ok = True
        for ch in channels:
            ok = await _check_bot_access(client, me.id, ch["username"])
            if ok:
                lines.append(f"✅ **{ch['label']}** (`{ch['username']}`) — Bot is admin, membership checks work.")
            else:
                all_ok = False
                lines.append(f"⚠️ **{ch['label']}** (`{ch['username']}`) — Bot is NOT admin here. Force-sub bypassed.")

        if all_ok:
            lines.append("\n✅ All channels are accessible. Force-sub is fully operational.")
        else:
            lines.append(
                "\n**Fix:** Go to each ⚠️ channel → Edit → Administrators → "
                "Add Admin → select the bot. Run `/checkfsub` again after fixing."
            )

        await message.reply_text("\n".join(lines), disable_web_page_preview=True)

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

        # ── Self-reference guard ─────────────────────────────────
        # Skip any channel whose username is the same as the current group.
        # A user is always a "member" of the group they're already in, so
        # keeping it as a force-sub requirement would bypass enforcement forever.
        try:
            chat_obj = await client.get_chat(chat_id)
            self_usernames: set[str] = set()
            if chat_obj.username:
                self_usernames.add(f"@{chat_obj.username}".lower())
            self_usernames.add(str(chat_id).lower())
        except Exception:
            self_usernames = set()

        skipped_self = [ch for ch in channels if ch["username"].lower() in self_usernames]
        channels = [ch for ch in channels if ch["username"].lower() not in self_usernames]

        if skipped_self:
            logger.warning(
                "chat %s — force-sub channels %s are the group itself and were skipped. "
                "Remove them with /clearfsub and re-add only external channels.",
                chat_id, [ch["username"] for ch in skipped_self]
            )
            # Warn admin in-group once about self-referencing config
            now = time.time()
            last_warn = _ADMIN_WARN_LAST.get(chat_id, 0)
            if now - last_warn >= ADMIN_WARN_COOLDOWN:
                _ADMIN_WARN_LAST[chat_id] = now
                names = ", ".join(f"`{ch['username']}`" for ch in skipped_self)
                try:
                    asyncio.create_task(client.send_message(
                        chat_id,
                        f"⚠️ **Force-sub config issue!**\n\n"
                        f"{names} is the same as this group — users are already members, so "
                        f"force-sub can never enforce it.\n\n"
                        f"**Fix:** Use `/clearfsub` then `/setfsub` with only your external "
                        f"channels/groups (not this group itself).\n\n"
                        f"_(This reminder appears once every 30 minutes.)_",
                        disable_web_page_preview=True,
                    ))
                except Exception as e:
                    logger.warning("Could not send self-ref warning: %s", e)

        if not channels:
            return  # all configured channels were the group itself — nothing to enforce

        lock = _get_lock(chat_id, user_id)
        async with lock:
            unjoined, inaccessible = await _get_unjoined(client, user_id, channels)

            logger.info(
                "fsub check — chat=%s user=%s unjoined=%s inaccessible=%s",
                chat_id, user_id,
                [ch["username"] for ch in unjoined],
                [ch["username"] for ch in inaccessible],
            )

            # If some channels can't be checked, warn the admin in-group (with cooldown).
            if inaccessible:
                now = time.time()
                last_warn = _ADMIN_WARN_LAST.get(chat_id, 0)
                if now - last_warn >= ADMIN_WARN_COOLDOWN:
                    _ADMIN_WARN_LAST[chat_id] = now
                    names = ", ".join(f"`{ch['username']}`" for ch in inaccessible)
                    try:
                        asyncio.create_task(client.send_message(
                            chat_id,
                            f"⚠️ **Force-sub setup issue detected!**\n\n"
                            f"The bot is **not an admin** in: {names}\n\n"
                            f"Force-sub is bypassed for those channels. To fix:\n"
                            f"Open each channel → Edit → Administrators → Add Admin → select the bot.\n\n"
                            f"Run `/checkfsub` to verify all channels are set up correctly.\n\n"
                            f"_(This reminder appears once every 30 minutes.)_",
                            disable_web_page_preview=True,
                        ))
                    except Exception as e:
                        logger.warning("Could not send admin warning: %s", e)

            if not unjoined:
                # Subscribed to everything accessible — clear stale state, reset escalation counter.
                _clear_state(chat_id, user_id)
                asyncio.create_task(db.reset_fsub_restrict_count(chat_id, user_id))
                return

            state = _get_state(chat_id, user_id)
            stage = state["stage"] if state else 0

            # Always delete the offending message first.
            await _safe_delete(client, chat_id, message.id)

            if stage == 0:
                # ── Stage 0: first warning notice with join buttons ──────
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
                # ── Stage 1: random sticker + refresh notice buttons ─────
                # Change 1 — Smart Join Buttons: edit the original notice to show
                # ONLY channels still unjoined (user may have joined one since Stage 0).
                notice_id = state.get("notice_id") if state else None
                if notice_id:
                    try:
                        await client.edit_message_reply_markup(
                            chat_id,
                            notice_id,
                            reply_markup=_join_keyboard(unjoined),
                        )
                    except (MessageIdInvalid, Exception):
                        pass  # notice already deleted — fine, sticker will still go out

                sticker_id = random.choice(_FORCE_SUB_STICKERS_RAW)
                sticker_msg = None
                # Try replying to the notice first
                if notice_id:
                    try:
                        sticker_msg = await client.send_sticker(
                            chat_id,
                            sticker_id,
                            reply_to_message_id=notice_id,
                        )
                    except (MessageIdInvalid, Exception) as e:
                        if not isinstance(e, MessageIdInvalid):
                            logger.error("Failed to send fsub sticker (with reply): %s", e)
                        sticker_msg = None
                # Fallback: send without reply
                if sticker_msg is None:
                    try:
                        sticker_msg = await client.send_sticker(chat_id, sticker_id)
                    except Exception as e:
                        logger.error("Failed to send fsub sticker (fallback): %s", e)
                if sticker_msg is not None:
                    asyncio.create_task(_delayed_delete(client, chat_id, sticker_msg.id, STICKER_TTL))
                _set_state(chat_id, user_id, stage=2, notice_id=notice_id)

            else:
                # ── Stage 2: escalating restriction ─────────────────────
                # Change 2+3: use until_date for timed restrictions (shows timer to user)
                # and escalate on each repeat offence.
                offense = await db.increment_fsub_restrict_count(chat_id, user_id)
                idx = min(offense - 1, len(ESCALATION_DURATIONS) - 1)
                duration = ESCALATION_DURATIONS[idx]

                _clear_state(chat_id, user_id)

                if duration is None:
                    # 3rd+ offense — permanent restriction
                    try:
                        await client.restrict_chat_member(
                            chat_id, user_id, MUTE_PERMISSIONS
                            # no until_date → permanent
                        )
                        await client.send_message(
                            chat_id,
                            f"🚫 {message.from_user.mention} has been **permanently restricted** "
                            f"for repeatedly ignoring the force-subscribe requirement.\n\n"
                            f"An admin can lift this with `/unmute` if they later join the channels.",
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.warning("Could not permanently restrict %s in %s: %s", user_id, chat_id, e)
                else:
                    # 1st / 2nd offense — timed restriction using until_date
                    # Telegram shows the user exactly when they'll be unmuted.
                    until = datetime.now(timezone.utc) + timedelta(seconds=duration)
                    label = "30 seconds"
                    try:
                        await client.restrict_chat_member(
                            chat_id, user_id, MUTE_PERMISSIONS,
                            until_date=until,
                        )
                        await client.send_message(
                            chat_id,
                            f"⏱️ {message.from_user.mention} has been muted for **{label}** "
                            f"(offense #{offense}) for ignoring the force-subscribe notice.\n\n"
                            f"Join the required channel(s) before the timer ends!",
                            disable_web_page_preview=True,
                        )
                    except Exception as e:
                        logger.warning("Could not restrict %s in %s: %s", user_id, chat_id, e)

        message.stop_propagation()
