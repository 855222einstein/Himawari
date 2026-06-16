# ============================================================
# Force Subscribe System
# plugin/force_sub/force_sub.py
#
# Features:
# - /addfsub @channel or ID  → add a channel/group to force-sub list
# - /rmfsub @channel or ID   → remove a channel/group from list
# - /fsub on / off           → enable or disable force sub
# - /fsublist                → show all force-sub channels for this group
# - New members get warned + join button (auto-delete 30s)
# - Messages from non-subscribers are deleted silently
# - Supports @username AND numeric IDs (e.g. -1001234567890)
# - Multiple channels/groups supported
# ============================================================

import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberUpdated,
    ChatPermissions,
)
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, PeerIdInvalid, UserAdminInvalid

from plugin.group_guard.group_guard import group_is_approved
from plugin.force_sub.db_force_sub import (
    set_force_sub,
    get_force_sub,
    disable_force_sub,
    enable_force_sub,
    add_force_sub_channel,
    remove_force_sub_channel,
    mark_force_sub_notice,
    clear_force_sub_notice,
    set_force_sub_message,
    get_force_sub_message,
    clear_all_force_sub_channels,
    set_force_sub_channel_label,
    get_force_sub_labels,
)

logger = logging.getLogger(__name__)

BORDER = "━━━━━━━━━━━━━━━━━━━━"


NOTICE_DELETE_SECONDS = 30
STICKER_DELETE_SECONDS = 10
MUTE_SECONDS = 30
IST = ZoneInfo("Asia/Kolkata")

# Runtime throttle state, keyed by (chat_id, user_id):
#   stage 0 -> force message just sent
#   stage 1 -> user ignored it and sent again -> sticker sent
#   stage 2 -> user ignored sticker too and sent again -> user muted 30s
# Once `expires_at` passes, the cycle resets and a fresh force
# message is shown the next time the user tries to chat.
_FORCE_NOTICE_STATE = {}

# Duplicate sticker IDs are skipped automatically.
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

FORCE_SUB_STICKERS = list(dict.fromkeys(_FORCE_SUB_STICKERS_RAW))
MORNING_STICKER = FORCE_SUB_STICKERS[0]


# ── Helpers ──────────────────────────────────────────────────

async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


def _parse_channel_arg(arg: str) -> str:
    """
    Accept @username, username (adds @), or numeric ID like -1001234567890.
    Returns clean identifier for Pyrogram.
    """
    arg = arg.strip()
    if arg.lstrip("-").isdigit():
        return int(arg)  # numeric ID
    if not arg.startswith("@"):
        return "@" + arg
    return arg


async def _get_join_url(client: Client, channel) -> str | None:
    """Get a joinable URL for a channel or group."""
    try:
        if isinstance(channel, str) and channel.startswith("@"):
            return f"https://t.me/{channel.lstrip('@')}"
        chat = await client.get_chat(channel)
        if chat.username:
            return f"https://t.me/{chat.username}"
        # Private channel/group — generate invite link
        invite = await client.export_chat_invite_link(chat.id)
        return invite
    except Exception as e:
        logger.warning("Could not get join URL for %s: %s", channel, e)
        return None


async def _is_subscribed(client: Client, channel, user_id: int) -> bool:
    """Check if user is member of a channel or group."""
    try:
        member = await client.get_chat_member(channel, user_id)
        return member.status not in (
            ChatMemberStatus.BANNED,
            ChatMemberStatus.LEFT,
        )
    except UserNotParticipant:
        return False
    except (PeerIdInvalid, ChatAdminRequired):
        return False
    except Exception as e:
        logger.warning("Force sub check error for %s: %s", channel, e)
        return True  # Don't block if check fails


async def _check_all_subscribed(client: Client, channels: list, user_id: int):
    """
    Returns list of channels the user has NOT joined yet.
    """
    not_joined = []
    for ch in channels:
        joined = await _is_subscribed(client, ch, user_id)
        if not joined:
            not_joined.append(ch)
    return not_joined


async def _build_join_buttons(client: Client, channels: list) -> list:
    """Build InlineKeyboardButton list for all unjoin channels."""
    buttons = []
    for i, ch in enumerate(channels, 1):
        url = await _get_join_url(client, ch)
        label = f"ᴊᴏɪɴ {i} 📢"
        try:
            chat = await client.get_chat(ch)
            label = f"ᴊᴏɪɴ : {chat.title} 📢"
        except Exception:
            pass
        if url:
            buttons.append([InlineKeyboardButton(label, url=url)])
    return buttons


def _pick_force_sub_sticker(chat_id: int, user_id: int) -> str | None:
    """Return a stable-but-rotating sticker. Morning always uses the first sticker."""
    if not FORCE_SUB_STICKERS:
        return None
    now = datetime.now(IST)
    if 5 <= now.hour < 12:
        return MORNING_STICKER
    seed = f"{chat_id}:{user_id}:{now.strftime('%Y-%m-%d')}:{now.hour // 3}"
    idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(FORCE_SUB_STICKERS)
    return FORCE_SUB_STICKERS[idx]


async def _send_force_sub_sticker(
    client: Client,
    chat_id: int,
    user_id: int,
    *,
    reply_to_message_id: int | None = None,
):
    sticker_id = _pick_force_sub_sticker(chat_id, user_id)
    if not sticker_id:
        return None
    try:
        sticker = await client.send_sticker(
            chat_id,
            sticker_id,
            reply_to_message_id=reply_to_message_id,
        )
        asyncio.create_task(_auto_delete(sticker, STICKER_DELETE_SECONDS))
        return sticker
    except Exception as e:
        logger.warning("Could not send force-sub sticker: %s", e)
        return None


async def _auto_delete(msg, delay=30):
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass


async def _mute_user_temporarily(client: Client, chat_id: int, user_id: int, seconds: int = MUTE_SECONDS):
    """Restrict a user from sending messages for `seconds` seconds."""
    until = datetime.now(IST) + timedelta(seconds=seconds)
    try:
        await client.restrict_chat_member(
            chat_id,
            user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until,
        )
    except (ChatAdminRequired, UserAdminInvalid) as e:
        logger.warning("Could not mute user %s in %s: %s", user_id, chat_id, e)
    except Exception as e:
        logger.warning("Force-sub mute failed for %s in %s: %s", user_id, chat_id, e)


async def _send_force_sub_notice(client: Client, message: Message, user, not_joined: list, *, is_join_event: bool = False):
    """
    Force-sub anti-spam flow:
    1) First blocked message -> send join request (force) message.
    2) Same user sends again within 30s -> bot sends one sticker as reply.
    3) Same user sends again (sticker also ignored) -> user is muted
       (can_send_messages disabled) for 30 seconds.
    4) Force message auto-deletes after 30s, sticker auto-deletes after 10s.
    5) After the cycle expires (~30s), the user's next blocked message
       gets a fresh force message again.
    """
    chat_id = message.chat.id
    user_id = user.id
    state_key = (chat_id, user_id)
    now_ts = datetime.now(IST).timestamp()

    state = _FORCE_NOTICE_STATE.get(state_key)
    if state and now_ts < state.get("expires_at", 0):
        stage = state.get("stage", 0)

        if stage == 0:
            # Second blocked attempt -> send a sticker as a nudge
            await _send_force_sub_sticker(
                client,
                chat_id,
                user_id,
                reply_to_message_id=state.get("message_id"),
            )
            state["stage"] = 1

        elif stage == 1:
            # Third+ attempt -> user ignored notice + sticker, mute briefly
            await _mute_user_temporarily(client, chat_id, user_id, MUTE_SECONDS)
            state["stage"] = 2

        # stage == 2 -> already muted, nothing further to do
        return

    buttons = await _build_join_buttons(client, not_joined)
    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    mention = f'<a href="tg://user?id={user.id}">{user.first_name}</a>'
    count = len(not_joined)
    join_text = "ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟ" if count == 1 else f"ᴀʟʟ {count} ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟs/ɢʀᴏᴜᴘs"
    heading = "ᴡᴇʟᴄᴏᴍᴇ" if is_join_event else "ʜᴇʏ"

    custom_template = await get_force_sub_message(chat_id)
    if custom_template:
        first_name = user.first_name or ""
        username = f"@{user.username}" if user.username else user.first_name or ""
        text = (
            custom_template
            .replace("{mention}", mention)
            .replace("{first_name}", first_name)
            .replace("{username}", username)
            .replace("{title}", message.chat.title or "")
            .replace("{count}", str(count))
            .replace("{channels}", join_text)
        )
    else:
        text = (
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            f"{heading} {mention}\n\n"
            f"ᴘʟᴇᴀsᴇ ᴊᴏɪɴ {join_text}\n"
            "ᴛᴏ sᴇɴᴅ ᴍᴇssᴀɢᴇs ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ.\n\n"
            "ᴜɴᴛɪʟ ʏᴏᴜ ᴊᴏɪɴ,\n"
            "ʏᴏᴜʀ ᴍᴇssᴀɢᴇs ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇᴅ.\n\n"
            "ɴᴏᴛᴇ : ᴍᴇssᴀɢᴇ 30 sᴇᴄᴏɴᴅs ᴍᴇ ᴅᴇʟᴇᴛᴇ ʜᴏ ᴊᴀʏᴇɢᴀ.\n"
            "ᴅᴜʙᴀʀᴀ ᴛʀʏ ᴋᴀʀɴᴇ ᴘᴀʀ sᴛɪᴄᴋᴇʀ ᴀᴀʏᴇɢᴀ.\n\n"
            f"{BORDER}"
        )

    warning = await client.send_message(
        chat_id,
        text,
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML,
    )

    _FORCE_NOTICE_STATE[state_key] = {
        "message_id": warning.id,
        "expires_at": now_ts + NOTICE_DELETE_SECONDS,
        "stage": 0,
    }
    await mark_force_sub_notice(chat_id, user_id)
    asyncio.create_task(_auto_delete(warning, NOTICE_DELETE_SECONDS))

    async def _clear_state_later():
        await asyncio.sleep(NOTICE_DELETE_SECONDS)
        current = _FORCE_NOTICE_STATE.get(state_key)
        if current and current.get("message_id") == warning.id:
            _FORCE_NOTICE_STATE.pop(state_key, None)

    asyncio.create_task(_clear_state_later())


# ── Registration ─────────────────────────────────────────────

def register_force_sub(app: Client):

    # ── /addfsub @channel or -100ID ───────────────────────────
    @app.on_message(filters.command("addfsub") & filters.group)
    async def cmd_addfsub(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return await message.reply_text("⏳ Group pending approval.")
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        if len(message.command) < 2:
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                "ᴜsᴀɢᴇ :\n"
                "/addfsub @channel\n"
                "/addfsub -1001234567890\n\n"
                "ʙᴏᴛ ᴍᴜsᴛ ʙᴇ ᴀᴅᴍɪɴ\n"
                "ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ/ɢʀᴏᴜᴘ.\n\n"
                f"{BORDER}"
            )

        channel = _parse_channel_arg(message.command[1])

        # Verify bot can access the channel/group
        try:
            chat = await client.get_chat(channel)
            channel_name = chat.title or str(channel)
            # Store as string for DB
            channel_str = f"@{chat.username}" if chat.username else str(chat.id)
        except Exception:
            return await message.reply_text(
                "❌ Cannot access that channel/group.\n"
                "Make sure bot is admin there."
            )

        await add_force_sub_channel(message.chat.id, channel_str)
        await enable_force_sub(message.chat.id)  # Auto-enable force-sub
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            "✅ ᴀᴅᴅᴇᴅ :\n"
            f"  {channel_name}\n\n"
            "ғᴏʀᴄᴇ sᴜʙ ɪs ɴᴏᴡ ᴀᴄᴛɪᴠᴇ ✅\n"
            "ᴜsᴇʀs ᴍᴜsᴛ ɴᴏᴡ ᴊᴏɪɴ\n"
            "ᴛʜɪs ᴄʜᴀɴɴᴇʟ ᴛᴏ ᴄʜᴀᴛ.\n\n"
            f"{BORDER}"
        )

    # ── /rmfsub @channel or -100ID ────────────────────────────
    @app.on_message(filters.command("rmfsub") & filters.group)
    async def cmd_rmfsub(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        if len(message.command) < 2:
            return await message.reply_text(
                "ᴜsᴀɢᴇ : /rmfsub @channel\n"
                "ᴏʀ     /rmfsub -1001234567890"
            )

        channel = _parse_channel_arg(message.command[1])

        try:
            chat = await client.get_chat(channel)
            channel_str = f"@{chat.username}" if chat.username else str(chat.id)
            channel_name = chat.title or channel_str
        except Exception:
            channel_str = str(channel)
            channel_name = channel_str

        await remove_force_sub_channel(message.chat.id, channel_str)
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            "🗑 ʀᴇᴍᴏᴠᴇᴅ :\n"
            f"  {channel_name}\n\n"
            f"{BORDER}"
        )

    # ── /fsub on | off ────────────────────────────────────────
    @app.on_message(filters.command("fsub") & filters.group)
    async def cmd_fsub(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        arg = message.command[1].lower() if len(message.command) > 1 else ""

        if arg == "off":
            await disable_force_sub(message.chat.id)
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                "sᴛᴀᴛᴜs : ᴅɪsᴀʙʟᴇᴅ 🔴\n\n"
                "ᴜsᴇʀs ᴄᴀɴ ɴᴏᴡ ᴄʜᴀᴛ\n"
                "ᴡɪᴛʜᴏᴜᴛ ᴊᴏɪɴɪɴɢ.\n\n"
                f"{BORDER}"
            )

        if arg == "on":
            await enable_force_sub(message.chat.id)
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                "sᴛᴀᴛᴜs : ᴀᴄᴛɪᴠᴇ ✅\n\n"
                "ᴜsᴇʀs ᴍᴜsᴛ ɴᴏᴡ ᴊᴏɪɴ\n"
                "ʙᴇꜰᴏʀᴇ ᴄʜᴀᴛᴛɪɴɢ.\n\n"
                f"{BORDER}"
            )

        # Show status
        cfg = await get_force_sub(message.chat.id)
        status = "ᴀᴄᴛɪᴠᴇ ✅" if cfg["enabled"] else "ɪɴᴀᴄᴛɪᴠᴇ 🔴"
        channels = cfg["channels"]
        ch_list = "\n".join(f"  • {c}" for c in channels) if channels else "  ɴᴏɴᴇ sᴇᴛ"

        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            f"sᴛᴀᴛᴜs : {status}\n\n"
            f"ᴄʜᴀɴɴᴇʟs :\n{ch_list}\n\n"
            "ᴄᴏᴍᴍᴀɴᴅs :\n"
            "/addfsub @channel\n"
            "/rmfsub @channel\n"
            "/fsub on | off\n"
            "/fsublist\n"
            "/setfsubmsg <text>\n"
            "/resetfsubmsg\n\n"
            f"{BORDER}"
        )

    # ── /setfsubmsg <text> ────────────────────────────────────
    # Customize the force-sub message shown to non-subscribers.
    # This is a separate command from /setwelcome, so the welcome
    # message and the force-sub message can be configured independently.
    @app.on_message(filters.command("setfsubmsg") & filters.group)
    async def cmd_setfsubmsg(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        text_input = message.text or message.caption or ""
        parts = text_input.split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                "ᴜsᴀɢᴇ :\n"
                "/setfsubmsg &lt;message&gt;\n\n"
                "ᴘʟᴀᴄᴇʜᴏʟᴅᴇʀs :\n"
                "{mention} — ᴜsᴇʀ ᴍᴇɴᴛɪᴏɴ\n"
                "{first_name} — ғɪʀsᴛ ɴᴀᴍᴇ\n"
                "{username} — @ᴜsᴇʀɴᴀᴍᴇ\n"
                "{title} — ɢʀᴏᴜᴘ ɴᴀᴍᴇ\n"
                "{count} — ᴄʜᴀɴɴᴇʟs ʟᴇғᴛ\n"
                "{channels} — ʀᴇǫᴜɪʀᴇᴅ ᴄʜᴀɴɴᴇʟ ᴛᴇxᴛ\n\n"
                "ᴜsᴇ /delfsubmsg ᴛᴏ ʀᴇsᴇᴛ.\n\n"
                f"{BORDER}"
            )

        await set_force_sub_message(message.chat.id, parts[1])
        preview = parts[1][:60] + ("..." if len(parts[1]) > 60 else "")
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            "✅ FORCE-SUB NOTICE MESSAGE SAVED!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"{preview}\n\n"
            f"{BORDER}"
        )

    # ── /resetfsubmsg ─────────────────────────────────────────
    @app.on_message(filters.command("resetfsubmsg") & filters.group)
    async def cmd_resetfsubmsg(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        await set_force_sub_message(message.chat.id, None)
        await message.reply_text("✅ Force-sub message reset to default.")

    # ── /fsublist ─────────────────────────────────────────────
    @app.on_message(filters.command("fsublist") & filters.group)
    async def cmd_fsublist(client: Client, message: Message):
        if not message.from_user:
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        cfg = await get_force_sub(message.chat.id)
        channels = cfg["channels"]
        status = "ᴀᴄᴛɪᴠᴇ ✅" if cfg["enabled"] else "ɪɴᴀᴄᴛɪᴠᴇ 🔴"

        if not channels:
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                "ɴᴏ ᴄʜᴀɴɴᴇʟs sᴇᴛ.\n"
                "ᴜsᴇ /addfsub ᴛᴏ ᴀᴅᴅ.\n\n"
                f"{BORDER}"
            )

        lines = []
        for i, ch in enumerate(channels, 1):
            try:
                chat = await client.get_chat(ch)
                lines.append(f"  {i}. {chat.title} ({ch})")
            except Exception:
                lines.append(f"  {i}. {ch}")

        ch_text = "\n".join(lines)
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ ʟɪsᴛ\n"
            f"{BORDER}\n\n"
            f"sᴛᴀᴛᴜs : {status}\n\n"
            f"ᴄʜᴀɴɴᴇʟs ({len(channels)}) :\n"
            f"{ch_text}\n\n"
            f"{BORDER}"
        )


    # ── /setfsub LABEL | @channel (Image-2 style) ─────────────────────────────
    @app.on_message(filters.command("setfsub") & filters.group)
    async def cmd_setfsub(client: Client, message: Message):
        import re as _re
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return await message.reply_text("⏳ Group pending approval.")
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")

        text_input = message.text or message.caption or ""
        parts = text_input.split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                "ᴜsᴀɢᴇ :\n"
                "/setfsub LABEL | @channel\n"
                "/setfsub DISCUSS | @discuss  UPDATE | @update\n\n"
                "ᴍᴜʟᴛɪᴘʟᴇ ᴄʜᴀɴɴᴇʟs — sᴇᴘᴀʀᴀᴛᴇ ᴡɪᴛʜ 2+ sᴘᴀᴄᴇs ᴏʀ ɴᴇᴡʟɪɴᴇ\n\n"
                f"{BORDER}"
            )

        raw = parts[1]
        pairs = _re.split(r"  +|\n", raw.strip())
        pairs = [p.strip() for p in pairs if p.strip()]

        added = []
        failed = []

        for pair in pairs:
            if "|" not in pair:
                failed.append(f"❌ {pair} (missing |)")
                continue
            label_part, ch_part = pair.split("|", 1)
            label = label_part.strip()
            ch_raw = ch_part.strip()
            if not label or not ch_raw:
                failed.append(f"❌ {pair} (empty label or channel)")
                continue
            channel = _parse_channel_arg(ch_raw)
            try:
                chat = await client.get_chat(channel)
                channel_str = f"@{chat.username}" if chat.username else str(chat.id)
                await set_force_sub_channel_label(message.chat.id, label, channel_str)
                added.append(f"✅ {label} → {channel_str}")
            except Exception:
                failed.append(f"❌ {label} | {ch_raw} (cannot access)")

        if added:
            await enable_force_sub(message.chat.id)

        lines = "\n".join(added + failed)
        status_line = "ғᴏʀᴄᴇ sᴜʙ ɪs ɴᴏᴡ ᴀᴄᴛɪᴠᴇ ✅" if added else "ɴᴏ ᴄʜᴀɴɴᴇʟs ᴀᴅᴅᴇᴅ ❌"
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            "ADDED:\n"
            f"{lines}\n\n"
            f"{status_line}\n\n"
            f"{BORDER}"
        )

    # ── /clearfsub ─────────────────────────────────────────────────────────────
    @app.on_message(filters.command("clearfsub") & filters.group)
    async def cmd_clearfsub(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")
        await clear_all_force_sub_channels(message.chat.id)
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            "🗑 ᴀʟʟ ᴄʜᴀɴɴᴇʟs ʀᴇᴍᴏᴠᴇᴅ.\n"
            "ғᴏʀᴄᴇ sᴜʙ ᴅɪsᴀʙʟᴇᴅ 🔴\n\n"
            f"{BORDER}"
        )

    # ── /viewfsub ──────────────────────────────────────────────────────────────
    @app.on_message(filters.command("viewfsub") & filters.group)
    async def cmd_viewfsub(client: Client, message: Message):
        if not message.from_user:
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")
        cfg = await get_force_sub(message.chat.id)
        channels = cfg["channels"]
        status = "ᴀᴄᴛɪᴠᴇ ✅" if cfg["enabled"] else "ɪɴᴀᴄᴛɪᴠᴇ 🔴"
        labels = await get_force_sub_labels(message.chat.id)
        custom_msg = await get_force_sub_message(message.chat.id)

        if not channels:
            return await message.reply_text(
                f"{BORDER}\n"
                "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
                f"{BORDER}\n\n"
                f"sᴛᴀᴛᴜs : {status}\n\n"
                "ɴᴏ ᴄʜᴀɴɴᴇʟs sᴇᴛ.\n"
                "ᴜsᴇ /setfsub ᴏʀ /addfsub ᴛᴏ ᴀᴅᴅ.\n\n"
                f"{BORDER}"
            )

        lines = []
        for i, ch in enumerate(channels, 1):
            key = ch.lstrip("@").replace("-", "_")
            label = labels.get(key, "")
            label_str = f" [{label}]" if label else ""
            try:
                chat_obj = await client.get_chat(ch)
                lines.append(f"  {i}. {chat_obj.title}{label_str} ({ch})")
            except Exception:
                lines.append(f"  {i}. {ch}{label_str}")

        ch_text = "\n".join(lines)
        msg_preview = (custom_msg[:80] + "...") if custom_msg and len(custom_msg) > 80 else (custom_msg or "ᴅᴇғᴀᴜʟᴛ")
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            f"sᴛᴀᴛᴜs : {status}\n\n"
            f"ᴄʜᴀɴɴᴇʟs ({len(channels)}) :\n"
            f"{ch_text}\n\n"
            f"ɴᴏᴛɪᴄᴇ ᴍsɢ : {msg_preview}\n\n"
            f"{BORDER}"
        )

    # ── /delfsubmsg (alias for /resetfsubmsg) ─────────────────────────────────
    @app.on_message(filters.command("delfsubmsg") & filters.group)
    async def cmd_delfsubmsg(client: Client, message: Message):
        if not message.from_user:
            return
        if not await group_is_approved(message.chat.id):
            return
        if not await _is_admin(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Admins only.")
        await set_force_sub_message(message.chat.id, None)
        await message.reply_text(
            f"{BORDER}\n"
            "ғᴏʀᴄᴇ • sᴜʙsᴄʀɪʙᴇ\n"
            f"{BORDER}\n\n"
            "✅ ɴᴏᴛɪᴄᴇ ᴍᴇssᴀɢᴇ ʀᴇsᴇᴛ\n"
            "ᴅᴇғᴀᴜʟᴛ ᴍᴇssᴀɢᴇ ʀᴇsᴛᴏʀᴇᴅ.\n\n"
            f"{BORDER}"
        )

    # ── Message watcher — delete & warn non-subscribers ───────
    @app.on_message(filters.group & ~filters.service, group=8)
    async def force_sub_watcher(client: Client, message: Message):
        if not message.from_user:
            return

        chat_id = message.chat.id
        user_id = message.from_user.id

        # Skip admins
        if await _is_admin(client, chat_id, user_id):
            return

        cfg = await get_force_sub(chat_id)
        if not cfg["enabled"] or not cfg["channels"]:
            return

        not_joined = await _check_all_subscribed(client, cfg["channels"], user_id)
        if not not_joined:
            await clear_force_sub_notice(chat_id, user_id)
            return

        # Delete user's message silently
        try:
            await message.delete()
        except Exception:
            pass

        # Send join request only once per user until the user joins.
        await _send_force_sub_notice(client, message, message.from_user, not_joined)

    # ── New member join ────────────────────────────────────────
    # NOTE: force-sub notice is intentionally NOT sent on join anymore.
    # It is only shown when the user actually tries to send a message
    # in the group (handled by force_sub_watcher above). This avoids
    # the force-sub message/sticker showing up alongside the welcome
    # message for new members.
    #
    # We DO reset any leftover notice/sticker/mute cycle state for the
    # joining user, so that if they (re)join and leftover state from a
    # previous cycle (e.g. quick leave+rejoin while testing) is still
    # "active", their next message still starts fresh: force message
    # first, sticker only if they ignore it and message again.
    @app.on_message(filters.new_chat_members & filters.group, group=8)
    async def new_member_reset_state(client: Client, message: Message):
        for user in message.new_chat_members:
            _FORCE_NOTICE_STATE.pop((message.chat.id, user.id), None)