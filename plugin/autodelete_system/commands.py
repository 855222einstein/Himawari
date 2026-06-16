# ============================================================
# Auto Delete System — Full Spec
# All 9 presets + custom time + /autodelete_on/off/custom
# Admin-only, groups/channels only
# ============================================================

import re
import logging
import random
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus, ChatType, ParseMode

from db_autodelete import (
    set_autodelete,
    get_autodelete,
    disable_autodelete,
    get_skip_admins,
    set_skip_admins,
)

logger = logging.getLogger(__name__)

# ── Timer presets (seconds) ────────────────────────────────
PRESETS = {
    "5m":   5 * 60,
    "30m":  30 * 60,
    "1h":   3600,
    "6h":   6 * 3600,
    "1d":   86400,
    "3d":   3 * 86400,
    "1w":   7 * 86400,
    "2w":   14 * 86400,
    "1mo":  30 * 86400,
}

MIN_SECONDS = 60           # 1 minute
MAX_SECONDS = 30 * 86400   # 30 days

# Waiting for custom input: {chat_id: user_id}
_awaiting_custom: dict[int, int] = {}


# ── Duration formatter ─────────────────────────────────────

def _format_duration(seconds: int) -> str:
    if seconds >= 30 * 86400:
        n = seconds // (30 * 86400)
        return f"{n} ᴍᴏɴᴛʜ" + ("ꜱ" if n > 1 else "")
    if seconds >= 7 * 86400:
        n = seconds // (7 * 86400)
        return f"{n} ᴡᴇᴇᴋ" + ("ꜱ" if n > 1 else "")
    if seconds >= 86400:
        n = seconds // 86400
        return f"{n} ᴅᴀʏ" + ("ꜱ" if n > 1 else "")
    if seconds >= 3600:
        n = seconds // 3600
        return f"{n} ʜᴏᴜʀ" + ("ꜱ" if n > 1 else "")
    n = seconds // 60
    return f"{n} ᴍɪɴᴜᴛᴇ" + ("ꜱ" if n > 1 else "")


# ── Custom time parser ─────────────────────────────────────
# Accepts: 10m 10min 10minutes | 2h 2hr 2hours | 3d 3days | 1w 1week | 1mo 2months

_CUSTOM_PATTERN = re.compile(
    r"^(\d+)\s*(mo|months?|w|weeks?|d|days?|h|hr|hours?|min|minutes?|m)$",
    re.IGNORECASE,
)

def _parse_custom_time(text: str) -> int | None:
    text = text.strip()
    m = _CUSTOM_PATTERN.match(text)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("mo"):
        return value * 30 * 86400
    if unit.startswith("w"):
        return value * 7 * 86400
    if unit.startswith("d"):
        return value * 86400
    if unit.startswith("h"):
        return value * 3600
    # minutes
    return value * 60


# ── Admin check ────────────────────────────────────────────

async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


def _is_group_chat(message: Message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL)


# ── Keyboards ──────────────────────────────────────────────

def _main_keyboard(skip_admins: bool = False) -> InlineKeyboardMarkup:
    sa_label = "ꜱᴋɪᴘ ᴀᴅᴍɪɴꜱ : ᴏɴ" if skip_admins else "ꜱᴋɪᴘ ᴀᴅᴍɪɴꜱ : ᴏꜰꜰ"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 ᴍɪɴ",   callback_data="ad:5m"),
            InlineKeyboardButton("30 ᴍɪɴ",  callback_data="ad:30m"),
            InlineKeyboardButton("1 ʜʀ",    callback_data="ad:1h"),
        ],
        [
            InlineKeyboardButton("6 ʜʀꜱ",   callback_data="ad:6h"),
            InlineKeyboardButton("1 ᴅᴀʏ",   callback_data="ad:1d"),
            InlineKeyboardButton("3 ᴅᴀʏꜱ",  callback_data="ad:3d"),
        ],
        [
            InlineKeyboardButton("1 ᴡᴋ",    callback_data="ad:1w"),
            InlineKeyboardButton("2 ᴡᴋꜱ",   callback_data="ad:2w"),
            InlineKeyboardButton("1 ᴍᴏ",    callback_data="ad:1mo"),
        ],
        [
            InlineKeyboardButton("ᴄᴜꜱᴛᴏᴍ ᴛɪᴍᴇ", callback_data="ad:custom"),
        ],
        [
            InlineKeyboardButton(sa_label, callback_data="ad:skipadmin"),
        ],
        [
            InlineKeyboardButton("ᴛᴜʀɴ ᴏꜰꜰ", callback_data="ad:off"),
        ],
    ])


# ── Response builders (HTML parse mode) ───────────────────

def _status_text(cfg: dict) -> str:
    status_line = "ᴀᴄᴛɪᴠᴇ" if (cfg["enabled"] and cfg["seconds"] > 0) else "ɪɴᴀᴄᴛɪᴠᴇ"
    timer_line  = _format_duration(cfg["seconds"]) if cfg["seconds"] > 0 else "—"
    sa_line     = "ᴏɴ" if cfg.get("skip_admins") else "ᴏꜰꜰ"

    return (
        "ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ꜱᴇᴛᴛɪɴɢꜱ\n\n"
        f"ꜱᴛᴀᴛᴜꜱ : {status_line}\n"
        f"ᴛɪᴍᴇʀ : {timer_line}\n"
        f"ꜱᴋɪᴘ ᴀᴅᴍɪɴꜱ : {sa_line}\n\n"
        "ᴄʜᴏᴏꜱᴇ ᴀ ᴛɪᴍᴇʀ ʙᴇʟᴏᴡ."
    )


def _enabled_text(duration: str) -> str:
    return (
        "ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴇɴᴀʙʟᴇᴅ\n\n"
        f"ꜱᴛᴀᴛᴜꜱ : ᴀᴄᴛɪᴠᴇ\n"
        f"ᴛɪᴍᴇʀ : {duration}\n\n"
        "/autodelete_off — ᴅɪꜱᴀʙʟᴇ\n"
        "/autodelete — ꜱᴇᴛᴛɪɴɢꜱ"
    )


def _disabled_text() -> str:
    return (
        "ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴅɪꜱᴀʙʟᴇᴅ\n\n"
        "ꜱᴛᴀᴛᴜꜱ : ɪɴᴀᴄᴛɪᴠᴇ\n\n"
        "ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪʟʟ ɴᴏ ʟᴏɴɢᴇʀ ʙᴇ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇᴅ.\n\n"
        "/autodelete_on — ʀᴇ-ᴇɴᴀʙʟᴇ\n"
        "/autodelete — ꜱᴇᴛᴛɪɴɢꜱ"
    )


# ── /autodelete [time?] — set timer OR open settings menu ──

async def cmd_autodelete(client: Client, message: Message):
    if not _is_group_chat(message):
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ ᴀɴᴅ ᴄʜᴀɴɴᴇʟꜱ ᴏɴʟʏ.")
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

    # If a time argument was given (e.g. /autodelete 5m), apply it directly
    parts = message.text.split(maxsplit=1)
    if len(parts) == 2:
        arg = parts[1].strip()
        seconds = _parse_custom_time(arg)
        if seconds is None or seconds < MIN_SECONDS:
            return await message.reply_text(
                f"ɪɴᴠᴀʟɪᴅ ꜰᴏʀᴍᴀᴛ : <code>{arg}</code>\n\n"
                "ᴠᴀʟɪᴅ ᴇxᴀᴍᴘʟᴇꜱ\n"
                "<code>5m</code>  <code>2h</code>  <code>3d</code>  <code>1w</code>  <code>1mo</code>\n\n"
                "ᴍɪɴ: 1 ᴍɪɴᴜᴛᴇ  ᴍᴀx: 30 ᴅᴀʏꜱ",
                parse_mode=ParseMode.HTML,
            )
        if seconds > MAX_SECONDS:
            return await message.reply_text(
                "ᴛɪᴍᴇʀ ᴛᴏᴏ ʟᴏɴɢ.\n\n"
                "ᴍᴀxɪᴍᴜᴍ ᴀʟʟᴏᴡᴇᴅ : 30 ᴅᴀʏꜱ.",
            )
        await set_autodelete(message.chat.id, "all", seconds, enabled=True)
        duration = _format_duration(seconds)
        cfg = await get_autodelete(message.chat.id)
        return await message.reply_text(
            _enabled_text(duration),
            reply_markup=_main_keyboard(cfg["skip_admins"]),
            parse_mode=ParseMode.HTML,
        )

    # No argument → open settings menu
    cfg = await get_autodelete(message.chat.id)
    await message.reply_text(
        _status_text(cfg),
        reply_markup=_main_keyboard(cfg["skip_admins"]),
        parse_mode=ParseMode.HTML,
    )


# ── /autodelete_on ─────────────────────────────────────────

async def cmd_autodelete_on(client: Client, message: Message):
    if not _is_group_chat(message):
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ ᴀɴᴅ ᴄʜᴀɴɴᴇʟꜱ ᴏɴʟʏ.")
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

    cfg = await get_autodelete(message.chat.id)
    seconds = cfg["seconds"] if cfg["seconds"] > 0 else PRESETS["1d"]
    await set_autodelete(message.chat.id, "all", seconds, enabled=True)
    duration = _format_duration(seconds)
    await message.reply_text(
        _enabled_text(duration),
        reply_markup=_main_keyboard(cfg["skip_admins"]),
        parse_mode=ParseMode.HTML,
    )


# ── /autodelete_off ────────────────────────────────────────

async def cmd_autodelete_off(client: Client, message: Message):
    if not _is_group_chat(message):
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ ᴀɴᴅ ᴄʜᴀɴɴᴇʟꜱ ᴏɴʟʏ.")
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

    await disable_autodelete(message.chat.id)
    await message.reply_text(_disabled_text(), parse_mode=ParseMode.HTML)


# ── /autodelete_custom ─────────────────────────────────────

async def cmd_autodelete_custom(client: Client, message: Message):
    if not _is_group_chat(message):
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ ᴀɴᴅ ᴄʜᴀɴɴᴇʟꜱ ᴏɴʟʏ.")
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

    _awaiting_custom[message.chat.id] = message.from_user.id
    await message.reply_text(
        "ꜱᴇɴᴅ ᴛʜᴇ ᴅᴜʀᴀᴛɪᴏɴ ɴᴏᴡ.\n\n"
        "<code>10m</code>  <code>10min</code>  <code>10minutes</code>\n"
        "<code>2h</code>  <code>2hr</code>  <code>2hours</code>\n"
        "<code>3d</code>  <code>3days</code>\n"
        "<code>1w</code>  <code>1week</code>\n"
        "<code>1mo</code>  <code>2months</code>\n\n"
        "ᴍɪɴ: 1 ᴍɪɴᴜᴛᴇ  ᴍᴀx: 30 ᴅᴀʏꜱ\n\n"
        "/autodelete — ᴄᴀɴᴄᴇʟ",
        parse_mode=ParseMode.HTML,
    )


# ── Custom time text handler ───────────────────────────────

async def handle_custom_time_input(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in _awaiting_custom:
        return
    if not message.from_user or message.from_user.id != _awaiting_custom[chat_id]:
        return

    del _awaiting_custom[chat_id]
    seconds = _parse_custom_time(message.text or "")

    if seconds is None or seconds < MIN_SECONDS:
        await message.reply_text(
            "ɪɴᴠᴀʟɪᴅ ꜰᴏʀᴍᴀᴛ.\n\n"
            "<code>10m</code>  <code>2h</code>  <code>3d</code>  <code>1w</code>  <code>1mo</code>\n\n"
            "ᴍɪɴɪᴍᴜᴍ : 1 ᴍɪɴᴜᴛᴇ\n\n"
            "/autodelete_custom — ᴛʀʏ ᴀɢᴀɪɴ",
            parse_mode=ParseMode.HTML,
        )
        return

    if seconds > MAX_SECONDS:
        await message.reply_text(
            "ᴛɪᴍᴇʀ ᴛᴏᴏ ʟᴏɴɢ.\n\n"
            "ᴍᴀxɪᴍᴜᴍ : 30 ᴅᴀʏꜱ.\n\n"
            "/autodelete_custom — ᴛʀʏ ᴀɢᴀɪɴ",
        )
        return

    await set_autodelete(chat_id, "all", seconds, enabled=True)
    duration = _format_duration(seconds)
    cfg = await get_autodelete(chat_id)
    await message.reply_text(
        _enabled_text(duration),
        reply_markup=_main_keyboard(cfg["skip_admins"]),
        parse_mode=ParseMode.HTML,
    )


# ── /autodelete_skipadmin ───────────────────────────────────

async def cmd_autodelete_skipadmin(client: Client, message: Message):
    if not _is_group_chat(message):
        return await message.reply_text("ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ ᴡᴏʀᴋꜱ ɪɴ ɢʀᴏᴜᴘꜱ ᴀɴᴅ ᴄʜᴀɴɴᴇʟꜱ ᴏɴʟʏ.")
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

    current = await get_skip_admins(message.chat.id)
    new_val = not current
    await set_skip_admins(message.chat.id, new_val)

    if new_val:
        await message.reply_text(
            "ꜱᴋɪᴘ ᴀᴅᴍɪɴꜱ : ᴏɴ\n\n"
            "ᴀᴅᴍɪɴ ᴀɴᴅ ᴏᴡɴᴇʀ ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪʟʟ ɴᴏᴛ ʙᴇ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇᴅ.\n\n"
            "/autodelete_skipadmin — ᴛᴏɢɢʟᴇ ᴏꜰꜰ",
        )
    else:
        await message.reply_text(
            "ꜱᴋɪᴘ ᴀᴅᴍɪɴꜱ : ᴏꜰꜰ\n\n"
            "ᴀᴅᴍɪɴ ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪʟʟ ɴᴏᴡ ʙᴇ ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇᴅ.\n\n"
            "/autodelete_skipadmin — ᴛᴏɢɢʟᴇ ᴏɴ",
        )


# ── Callback handler ───────────────────────────────────────

async def callback_autodelete(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        await query.answer("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.", show_alert=True)
        return

    data = query.data

    if data == "ad:off":
        await disable_autodelete(chat_id)
        await query.answer("ᴅɪꜱᴀʙʟᴇᴅ", show_alert=False)
        await query.message.edit_text(
            _disabled_text(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "ad:skipadmin":
        current = await get_skip_admins(chat_id)
        new_val = not current
        await set_skip_admins(chat_id, new_val)
        label = "ᴏɴ" if new_val else "ᴏꜰꜰ"
        await query.answer(f"ꜱᴋɪᴘ ᴀᴅᴍɪɴꜱ : {label}", show_alert=False)
        cfg = await get_autodelete(chat_id)
        await query.message.edit_text(
            _status_text(cfg),
            reply_markup=_main_keyboard(cfg["skip_admins"]),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "ad:custom":
        _awaiting_custom[chat_id] = user_id
        await query.answer("ꜱᴇɴᴅ ᴅᴜʀᴀᴛɪᴏɴ ɴᴏᴡ", show_alert=False)
        await query.message.reply_text(
            "ꜱᴇɴᴅ ᴛʜᴇ ᴅᴜʀᴀᴛɪᴏɴ ɴᴏᴡ.\n\n"
            "<code>10m</code>  <code>10min</code>  <code>2h</code>  <code>3d</code>  <code>1w</code>  <code>1mo</code>\n\n"
            "ᴍɪɴ: 1 ᴍɪɴᴜᴛᴇ  ᴍᴀx: 30 ᴅᴀʏꜱ",
            parse_mode=ParseMode.HTML,
        )
        return

    # Strip "ad:" prefix → get PRESETS key (e.g. "ad:5m" → "5m")
    key = data[3:]
    if key in PRESETS:
        seconds = PRESETS[key]
        await set_autodelete(chat_id, "all", seconds, enabled=True)
        duration = _format_duration(seconds)
        await query.answer(duration, show_alert=False)
        cfg = await get_autodelete(chat_id)
        await query.message.edit_text(
            _enabled_text(duration),
            reply_markup=_main_keyboard(cfg["skip_admins"]),
            parse_mode=ParseMode.HTML,
        )


# ── Registration ───────────────────────────────────────────

def register_autodelete_system(app: Client):
    app.on_message(filters.command("autodelete"))(cmd_autodelete)
    app.on_message(filters.command("autodelete_on"))(cmd_autodelete_on)
    app.on_message(filters.command("autodelete_off"))(cmd_autodelete_off)
    app.on_message(filters.command("autodelete_custom"))(cmd_autodelete_custom)
    app.on_message(filters.command("autodelete_skipadmin"))(cmd_autodelete_skipadmin)

    app.on_message(
        filters.text & filters.group & ~filters.command(""),
        group=5,
    )(handle_custom_time_input)

    app.on_callback_query(filters.regex(r"^ad:"))(callback_autodelete)
    logger.info("✅ AutoDelete system registered.")
