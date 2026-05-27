# ============================================================
# Group Manager Bot — Auto Delete System
# plugin/autodelete_system/commands.py
#
# Clean 4-button keyboard: 1 Day | 1 Week | 1 Month | Custom
# Deletes: text, photos, videos, documents, stickers, charts
# Admin-only. All message types covered.
# ============================================================

import re
import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus

from db_autodelete import (
    set_autodelete,
    get_autodelete,
    disable_autodelete,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────
SECONDS_1DAY   = 86_400
SECONDS_1WEEK  = 604_800
SECONDS_1MONTH = 2_592_000   # 30 days

# Waiting for custom input: {chat_id: user_id}
_awaiting_custom: dict[int, int] = {}


# ── Helpers ────────────────────────────────────────────────

def _format_duration(seconds: int) -> str:
    if seconds >= SECONDS_1MONTH:
        return f"{seconds // SECONDS_1MONTH} month(s)"
    if seconds >= SECONDS_1WEEK:
        return f"{seconds // SECONDS_1WEEK} week(s)"
    if seconds >= SECONDS_1DAY:
        return f"{seconds // SECONDS_1DAY} day(s)"
    if seconds >= 3600:
        return f"{seconds // 3600} hour(s)"
    return f"{seconds // 60} minute(s)"


def _parse_custom_time(text: str) -> int | None:
    text = text.strip().lower()
    match = re.fullmatch(r"(\d+)(m|h|d|w|mo)", text)
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800, "mo": 2592000}
    return value * multipliers[unit]


async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


# ── Clean 4-button keyboard (proper sizing) ───────────────

def _main_keyboard() -> InlineKeyboardMarkup:
    """
    4 time buttons in 2x2 grid + Turn Off full width.
    Short labels = buttons fit perfectly on all screen sizes.
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏱ 1 Day",    callback_data="ad:1d"),
            InlineKeyboardButton("📅 1 Week",   callback_data="ad:1w"),
        ],
        [
            InlineKeyboardButton("🗓 1 Month",  callback_data="ad:1mo"),
            InlineKeyboardButton("✏️ Custom",   callback_data="ad:custom"),
        ],
        [
            InlineKeyboardButton("🔴 Turn Off", callback_data="ad:off"),
        ],
    ])


def _confirm_text(duration: str, seconds: int) -> str:
    return (
        f"✅ **Auto Delete Enabled**\n\n"
        f"🗑️ New messages, photos, videos, files & stickers\n"
        f"⏳ will be deleted after **{duration}**\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"_Use /autodelete\\_off to disable_"
    )


# ── Admin-only decorator ───────────────────────────────────

def admin_only(func):
    async def wrapper(client: Client, message: Message):
        if message.chat.type.value == "private":
            await message.reply_text("⚠️ Groups/channels only.")
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            await message.reply_text("🚫 Admins only.")
            return
        await func(client, message)
    return wrapper


# ── Apply + reply helper ───────────────────────────────────

async def _apply_and_reply(client: Client, message: Message, seconds: int):
    await set_autodelete(message.chat.id, "all", seconds, enabled=True)
    duration = _format_duration(seconds)
    await message.reply_text(
        _confirm_text(duration, seconds),
        reply_markup=_main_keyboard(),
    )


# ── /autodelete — main menu ────────────────────────────────

@admin_only
async def cmd_autodelete(client: Client, message: Message):
    cfg = await get_autodelete(message.chat.id)
    if cfg["enabled"]:
        status = f"🟢 **Active** — deletes after {_format_duration(cfg['seconds'])}"
    else:
        status = "🔴 **Inactive**"

    await message.reply_text(
        f"🗑️ **Auto Delete Settings**\n\n"
        f"Status: {status}\n\n"
        f"Choose how long messages stay:",
        reply_markup=_main_keyboard(),
    )


# ── ON / OFF ───────────────────────────────────────────────

@admin_only
async def cmd_autodelete_on(client: Client, message: Message):
    cfg = await get_autodelete(message.chat.id)
    if cfg["seconds"] == 0:
        cfg["seconds"] = SECONDS_1DAY
        cfg["mode"] = "all"
    await set_autodelete(message.chat.id, cfg["mode"], cfg["seconds"], enabled=True)
    duration = _format_duration(cfg["seconds"])
    await message.reply_text(
        f"✅ **Auto Delete Re-enabled**\n\n"
        f"🗑️ Messages, photos, videos, files\n"
        f"⏳ Delete after: **{duration}**\n\n"
        f"_Use /autodelete\\_off to disable_",
        reply_markup=_main_keyboard(),
    )


@admin_only
async def cmd_autodelete_off(client: Client, message: Message):
    await disable_autodelete(message.chat.id)
    await message.reply_text(
        "🔴 **Auto Delete Disabled**\n\n"
        "Messages will no longer be deleted.\n\n"
        "_Use /autodelete\\_on to re-enable_"
    )


# ── Time commands ──────────────────────────────────────────

@admin_only
async def cmd_autodelete_1day(client, message):
    await _apply_and_reply(client, message, SECONDS_1DAY)

@admin_only
async def cmd_autodelete_1week(client, message):
    await _apply_and_reply(client, message, SECONDS_1WEEK)

@admin_only
async def cmd_autodelete_1month(client, message):
    await _apply_and_reply(client, message, SECONDS_1MONTH)


# ── Custom time ────────────────────────────────────────────

@admin_only
async def cmd_autodelete_custom(client: Client, message: Message):
    _awaiting_custom[message.chat.id] = message.from_user.id
    await message.reply_text(
        "✏️ **Custom Delete Time**\n\n"
        "Type the duration:\n\n"
        "`10m` → 10 minutes\n"
        "`12h` → 12 hours\n"
        "`7d`  → 7 days\n"
        "`2w`  → 2 weeks\n"
        "`1mo` → 1 month\n\n"
        "_Send your time now:_"
    )


async def handle_custom_time_input(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in _awaiting_custom:
        return
    if message.from_user.id != _awaiting_custom[chat_id]:
        return

    del _awaiting_custom[chat_id]
    seconds = _parse_custom_time(message.text or "")

    if seconds is None or seconds < 60:
        await message.reply_text(
            "❌ **Invalid format.**\n\n"
            "Use: `10m` `12h` `7d` `2w` `1mo`\n"
            "Min: 1 minute\n\n"
            "_Run /autodelete\\_custom to try again_"
        )
        return

    await _apply_and_reply(client, message, seconds)


# ── Callback handler ───────────────────────────────────────

CALLBACK_SECONDS = {
    "ad:1d":  SECONDS_1DAY,
    "ad:1w":  SECONDS_1WEEK,
    "ad:1mo": SECONDS_1MONTH,
}


async def callback_autodelete(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    if not await _is_admin(client, chat_id, user_id):
        await query.answer("🚫 Admins only.", show_alert=True)
        return

    data = query.data

    # ── Turn Off ──
    if data == "ad:off":
        await disable_autodelete(chat_id)
        await query.answer("🔴 Disabled", show_alert=False)
        await query.message.edit_text(
            "🔴 **Auto Delete Disabled**\n\n"
            "Messages will no longer be deleted.\n\n"
            "_Use /autodelete\\_on to re-enable_"
        )
        return

    # ── Custom ──
    if data == "ad:custom":
        _awaiting_custom[chat_id] = user_id
        await query.answer("✏️ Send duration now", show_alert=False)
        await query.message.reply_text(
            "✏️ **Custom Delete Time**\n\n"
            "Type: `10m` `12h` `7d` `2w` `1mo`"
        )
        return

    # ── Time preset ──
    if data in CALLBACK_SECONDS:
        seconds = CALLBACK_SECONDS[data]
        await set_autodelete(chat_id, "all", seconds, enabled=True)
        duration = _format_duration(seconds)
        await query.answer(f"✅ {duration}", show_alert=False)
        await query.message.edit_text(
            _confirm_text(duration, seconds),
            reply_markup=_main_keyboard(),
        )


# ── Registration ───────────────────────────────────────────

def register_autodelete_system(app: Client):
    app.on_message(filters.command("autodelete"))(cmd_autodelete)
    app.on_message(filters.command("autodelete_on"))(cmd_autodelete_on)
    app.on_message(filters.command("autodelete_off"))(cmd_autodelete_off)
    app.on_message(filters.command("autodelete_1day"))(cmd_autodelete_1day)
    app.on_message(filters.command("autodelete_1week"))(cmd_autodelete_1week)
    app.on_message(filters.command("autodelete_1month"))(cmd_autodelete_1month)
    app.on_message(filters.command("autodelete_custom"))(cmd_autodelete_custom)

    app.on_message(
        filters.text & filters.group & ~filters.command(""),
        group=5,
    )(handle_custom_time_input)

    app.on_callback_query(filters.regex(r"^ad:"))(callback_autodelete)
    logger.info("✅ AutoDelete system registered.")
