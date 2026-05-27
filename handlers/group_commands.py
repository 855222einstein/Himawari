# ============================================================
# Group Manager Bot
# Fixed Welcome + Welcome Buttons
# ============================================================

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    ChatMemberUpdated,
    ChatPermissions,
    ChatPrivileges,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram.enums import ChatMemberStatus
import logging
import re
import db
from plugin.group_guard.group_guard import group_is_approved

DEFAULT_WELCOME = "👋 Welcome {mention} to {title}!"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


async def _check_approved(message) -> bool:
    """Returns True if approved. Sends rejection notice and returns False otherwise."""
    if await group_is_approved(message.chat.id):
        return True
    status = await db.get_group_approval(message.chat.id)
    if status == "rejected":
        await message.reply_text("🚫 This group has been **rejected** and cannot use bot features.")
    else:
        await message.reply_text(
            "⏳ This group is **pending approval**.\n"
            "Commands are disabled until the bot owner approves this group."
        )
    return False


async def is_power(client, chat_id: int, user_id: int) -> bool:
    member = await client.get_chat_member(chat_id, user_id)
    return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]


async def extract_target_user(client, message: Message):
    if message.reply_to_message:
        return message.reply_to_message.from_user

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return None

    arg = parts[1].strip()
    try:
        if arg.startswith("@"):
            return await client.get_users(arg)
        if arg.isdigit():
            return await client.get_users(int(arg))
    except Exception:
        return None


def is_valid_url(url: str) -> bool:
    return url.startswith(("http://", "https://", "tg://"))


def parse_button_lines(raw_text: str):
    """
    Supported formats:

    1 button:
    /setwelcomebutton Main Channel | https://t.me/shinchan_leech

    Multiple buttons:
    /setwelcomebutton
    YouTube Channel | https://youtube.com/xxx
    Tutorial Channel | https://t.me/xxx

    2 buttons in one row:
    Button 1 | https://link1.com && Button 2 | https://link2.com
    """
    rows = []
    errors = []

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        row = []
        parts = [p.strip() for p in line.split("&&") if p.strip()]

        for part in parts:
            if "|" not in part:
                errors.append(f"❌ `{part}` — format galat hai. Use: Button Name | https://link.com")
                continue

            name, url = part.split("|", 1)
            name = name.strip()
            url = url.strip()

            if not name:
                errors.append(f"❌ Button name empty hai: `{part}`")
                continue

            if not is_valid_url(url):
                errors.append(f"❌ Invalid URL `{url}` — URL http://, https:// ya tg:// se start hona chahiye")
                continue

            row.append({"text": name, "url": url})

        if row:
            rows.append(row)

    return rows, errors


async def build_welcome_keyboard(chat_id: int):
    saved_rows = await db.get_welcome_buttons(chat_id)
    if not saved_rows:
        return None

    keyboard = []

    # Old database support: [{"text": "...", "url": "..."}]
    if isinstance(saved_rows, list) and saved_rows and isinstance(saved_rows[0], dict):
        for btn in saved_rows:
            text = btn.get("text")
            url = btn.get("url")
            if text and url and is_valid_url(url):
                keyboard.append([InlineKeyboardButton(text, url=url)])

    # New database support: [[{"text": "...", "url": "..."}]]
    elif isinstance(saved_rows, list):
        for row in saved_rows:
            if not isinstance(row, list):
                continue
            btn_row = []
            for btn in row:
                if not isinstance(btn, dict):
                    continue
                text = btn.get("text")
                url = btn.get("url")
                if text and url and is_valid_url(url):
                    btn_row.append(InlineKeyboardButton(text, url=url))
            if btn_row:
                keyboard.append(btn_row)

    return InlineKeyboardMarkup(keyboard) if keyboard else None


async def handle_welcome(client, chat_id: int, users: list, chat_title: str):
    status = await db.get_welcome_status(chat_id)
    if not status:
        return

    welcome_text = await db.get_welcome_message(chat_id) or DEFAULT_WELCOME
    reply_markup = await build_welcome_keyboard(chat_id)

    for user in users:
        try:
            text = welcome_text.format(
                first_name=user.first_name or "",
                last_name=user.last_name or "",
                username=user.username or user.first_name or "",
                mention=user.mention,
                id=user.id,
                title=chat_title or "",
            )
        except Exception as e:
            logger.warning("Welcome format error: %s", e)
            text = DEFAULT_WELCOME.format(
                mention=user.mention,
                title=chat_title or "",
            )

        try:
            await client.send_message(
                chat_id,
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error("Failed to send welcome: %s", e)


def register_group_commands(app: Client):

    @app.on_chat_member_updated()
    async def member_update(client: Client, cmu: ChatMemberUpdated):
        if not cmu.new_chat_member:
            return

        user = cmu.new_chat_member.user
        old_status = cmu.old_chat_member.status if cmu.old_chat_member else None
        new_status = cmu.new_chat_member.status

        if new_status == ChatMemberStatus.MEMBER and old_status != ChatMemberStatus.MEMBER:
            await handle_welcome(client, cmu.chat.id, [user], cmu.chat.title)

    @app.on_message(filters.group & filters.new_chat_members)
    async def new_member_message(client: Client, message: Message):
        if not await group_is_approved(message.chat.id):
            return  # silently skip unapproved groups
        await handle_welcome(
            client,
            message.chat.id,
            message.new_chat_members,
            message.chat.title,
        )

    @app.on_message(filters.group & filters.command("welcome"))
    async def welcome_toggle(client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2 or parts[1].lower() not in ["on", "off"]:
            return await message.reply_text("Usage: /welcome on or /welcome off")

        status = parts[1].lower() == "on"
        await db.set_welcome_status(message.chat.id, status)
        await message.reply_text("✅ Welcome messages ON." if status else "⚠️ Welcome messages OFF.")

    @app.on_message(filters.group & filters.command("setwelcome"))
    async def set_welcome(client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text(
                "Usage:\n"
                "/setwelcome Hey {mention}\n"
                "Welcome To {title}"
            )

        await db.set_welcome_message(message.chat.id, parts[1])
        await message.reply_text("✅ Custom welcome saved!")

    @app.on_message(filters.group & filters.command("setwelcomebutton"))
    async def set_welcome_button(client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")

        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            return await message.reply_text(
                "✅ Sahi format:\n"
                "/setwelcomebutton Main Channel | https://t.me/shinchan_leech\n\n"
                "Multiple buttons:\n"
                "/setwelcomebutton\n"
                "YouTube Channel | https://youtube.com/@yourchannel\n"
                "Tutorial Channel | https://t.me/tutorial\n\n"
                "Same row buttons:\n"
                "Button 1 | https://link1.com && Button 2 | https://link2.com"
            )

        rows, errors = parse_button_lines(parts[1])

        if not rows:
            msg = (
                "⚠️ Koi valid button nahi mila.\n\n"
                "Format: Button Name | https://link.com\n\n"
                "Example:\n"
                "/setwelcomebutton Main Channel | https://t.me/shinchan_leech"
            )
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors)
            return await message.reply_text(msg, disable_web_page_preview=True)

        await db.set_welcome_buttons(message.chat.id, rows)

        total = sum(len(row) for row in rows)
        btn_list = []
        for row in rows:
            btn_list.append(" | ".join([f"{b['text']} → {b['url']}" for b in row]))

        reply = f"✅ {total} welcome button(s) save ho gaye!\n\n" + "\n".join(btn_list)
        if errors:
            reply += "\n\n⚠️ Kuch lines skip hui:\n" + "\n".join(errors)

        await message.reply_text(reply, disable_web_page_preview=True)

    @app.on_message(filters.group & filters.command("clearwelcomebutton"))
    async def clear_welcome_button(client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")

        await db.clear_welcome_buttons(message.chat.id)
        await message.reply_text("🗑️ Welcome buttons hata diye gaye!")

    @app.on_message(filters.group & filters.command("welcomebuttons"))
    async def show_welcome_buttons(client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")

        saved = await db.get_welcome_buttons(message.chat.id)
        if not saved:
            return await message.reply_text("ℹ️ Koi welcome button set nahi hai.")

        lines = []
        if saved and isinstance(saved[0], dict):
            for i, b in enumerate(saved, 1):
                lines.append(f"{i}. {b['text']} → {b['url']}")
        else:
            n = 1
            for row in saved:
                for b in row:
                    lines.append(f"{n}. {b['text']} → {b['url']}")
                    n += 1

        await message.reply_text("📋 Current buttons:\n\n" + "\n".join(lines), disable_web_page_preview=True)

    # /kick
    @app.on_message(filters.group & filters.command("kick"))
    async def kick_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /kick @username")
        target_member = await client.get_chat_member(message.chat.id, user.id)
        if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("⚠️ Cannot kick admins.")
        if user.id == message.from_user.id:
            return await message.reply_text("⚠️ Cannot kick yourself.")
        try:
            await client.ban_chat_member(message.chat.id, user.id)
            await client.unban_chat_member(message.chat.id, user.id)
            await message.reply_text(f"👢 {user.mention} kicked.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")

    # /ban
    @app.on_message(filters.group & filters.command("ban"))
    async def ban_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /ban @username")
        target_member = await client.get_chat_member(message.chat.id, user.id)
        if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("⚠️ Cannot ban admins.")
        if user.id == message.from_user.id:
            return await message.reply_text("⚠️ Cannot ban yourself.")
        try:
            await client.ban_chat_member(message.chat.id, user.id)
            await message.reply_text(f"🚨 {user.mention} banned.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")

    # /unban
    @app.on_message(filters.group & filters.command("unban"))
    async def unban_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /unban @username")
        try:
            await client.unban_chat_member(message.chat.id, user.id)
            await message.reply_text(f"✅ {user.mention} unbanned.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")

    # /mute
    @app.on_message(filters.group & filters.command("mute"))
    async def mute_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /mute @username")
        target_member = await client.get_chat_member(message.chat.id, user.id)
        if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("⚠️ Cannot mute admins.")
        if user.id == message.from_user.id:
            return await message.reply_text("⚠️ Cannot mute yourself.")
        try:
            await client.restrict_chat_member(message.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await message.reply_text(f"🔇 {user.mention} muted.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")

    # /unmute
    @app.on_message(filters.group & filters.command("unmute"))
    async def unmute_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /unmute @username")
        try:
            await client.restrict_chat_member(message.chat.id, user.id, permissions=ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_other_messages=True, can_add_web_page_previews=True))
            await message.reply_text(f"🔊 {user.mention} unmuted.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")

    # /warn
    @app.on_message(filters.group & filters.command("warn"))
    async def warn_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /warn @username")
        target_member = await client.get_chat_member(message.chat.id, user.id)
        if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("⚠️ Cannot warn admins.")
        if user.id == message.from_user.id:
            return await message.reply_text("⚠️ Cannot warn yourself.")
        warns = await db.add_warn(message.chat.id, user.id)
        if warns >= 3:
            await client.restrict_chat_member(message.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
            await message.reply_text(f"🚫 {user.mention} 3 warns — muted.")
        else:
            await message.reply_text(f"⚠️ {user.mention} {warns}/3 warnings.")

    # /warns
    @app.on_message(filters.group & filters.command("warns"))
    async def warns_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /warns @username")
        warns = await db.get_warns(message.chat.id, user.id)
        await message.reply_text(f"⚠️ {user.mention} has {warns}/3 warnings.")

    # /resetwarns
    @app.on_message(filters.group & filters.command("resetwarns"))
    async def resetwarns_user(client, message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /resetwarns @username")
        await db.reset_warns(message.chat.id, user.id)
        await message.reply_text(f"✅ {user.mention} warns reset.")

    # /promote
    @app.on_message(filters.group & filters.command("promote"))
    async def promote_user(client: Client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /promote @username")
        target_member = await client.get_chat_member(message.chat.id, user.id)
        if target_member.status == ChatMemberStatus.OWNER:
            return await message.reply_text("⚠️ Cannot promote owner.")
        if user.id == message.from_user.id:
            return await message.reply_text("⚠️ Cannot promote yourself.")
        try:
            await client.promote_chat_member(chat_id=message.chat.id, user_id=user.id, privileges=ChatPrivileges(
                can_manage_chat=True, can_delete_messages=True, can_manage_video_chats=True,
                can_restrict_members=True, can_promote_members=False, can_change_info=True,
                can_invite_users=True, can_pin_messages=True, is_anonymous=False))
            await message.reply_text(f"✅ {user.mention} promoted to admin.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")

    # /demote
    @app.on_message(filters.group & filters.command("demote"))
    async def demote_user(client: Client, message: Message):
        if not await _check_approved(message):
            return
        if not await is_power(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admin can use this command.")
        user = await extract_target_user(client, message)
        if not user:
            return await message.reply_text("Usage: Reply or /demote @username")
        try:
            target_member = await client.get_chat_member(message.chat.id, user.id)
        except Exception as e:
            return await message.reply_text(f"❌ Failed: {e}")
        if target_member.status == ChatMemberStatus.OWNER:
            return await message.reply_text("⚠️ Cannot demote owner.")
        if target_member.status != ChatMemberStatus.ADMINISTRATOR:
            return await message.reply_text("⚠️ User is not an admin.")
        if user.id == message.from_user.id:
            return await message.reply_text("⚠️ Cannot demote yourself.")
        try:
            await client.promote_chat_member(chat_id=message.chat.id, user_id=user.id, privileges=ChatPrivileges(
                can_manage_chat=False, can_delete_messages=False, can_manage_video_chats=False,
                can_restrict_members=False, can_promote_members=False, can_change_info=False,
                can_invite_users=False, can_pin_messages=False, is_anonymous=False))
            await message.reply_text(f"✅ {user.mention} demoted.")
        except Exception as e:
            await message.reply_text(f"❌ Failed: {e}")
