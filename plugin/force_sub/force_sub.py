# ============================================================
# Force Subscribe Plugin
# Flow:
#   1. New member joins → check subscription to all channels
#   2. Not subscribed → MUTE user + show notice + "✅ I've Joined" button
#   3. Subscribed → show welcome with channel buttons (no mute)
#   4. Callback "fsub_verify:<chat_id>:<user_id>" → re-check → unmute + welcome
# Commands:
#   /setfsub  LABEL | @channel  LABEL2 | @channel2
#   /clearfsub
#   /setfsubmsg  <text>  (supports {mention} {first_name} {username} {title})
#   /delfsubmsg
#   /viewfsub
# ============================================================

import logging
import re
from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelPrivate
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
)
import db
from plugin.group_guard.group_guard import group_is_approved

logger = logging.getLogger(__name__)

DEFAULT_FSUB_MSG = (
    "Hey {mention} 👋\n\n"
    "You need to join our channel(s) before using this group.\n\n"
    "Please join all channels below, then tap **✅ I've Joined**."
)

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


def _join_keyboard(channels: list, chat_id: int, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        rows.append([InlineKeyboardButton(
            f"📢 {ch['label']}",
            url=_channel_url(ch["username"])
        )])
    rows.append([InlineKeyboardButton(
        "✅ I've Joined",
        callback_data=f"fsub_verify:{chat_id}:{user_id}"
    )])
    return InlineKeyboardMarkup(rows)


def _welcome_keyboard(channels: list) -> InlineKeyboardMarkup:
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

    # ── New member join — mute if not subscribed ──────────────
    @app.on_message(filters.group & filters.new_chat_members, group=1)
    async def fsub_new_member(client, message: Message):
        if not await group_is_approved(message.chat.id):
            return

        channels = await db.get_fsub_channels(message.chat.id)
        if not channels:
            return  # force-sub not configured

        me = await client.get_me()
        fsub_text = await db.get_fsub_message(message.chat.id) or DEFAULT_FSUB_MSG

        for user in message.new_chat_members:
            if user.id == me.id:
                continue
            if user.is_bot:
                continue

            unjoined = await _get_unjoined(client, user.id, channels)

            if unjoined:
                # MUTE the user until they join required channels
                try:
                    await client.restrict_chat_member(
                        message.chat.id,
                        user.id,
                        MUTE_PERMISSIONS,
                    )
                except Exception as e:
                    logger.warning("Could not mute user %s: %s", user.id, e)

                notice = _format_text(fsub_text, user, message.chat.title)
                keyboard = _join_keyboard(unjoined, message.chat.id, user.id)
                try:
                    await client.send_message(
                        message.chat.id,
                        notice,
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.error("Failed to send fsub notice: %s", e)

            else:
                # Already subscribed — show welcome with channel buttons
                welcome_text = await db.get_welcome_message(message.chat.id)
                if not welcome_text:
                    welcome_text = fsub_text
                text = _format_text(welcome_text, user, message.chat.title)
                keyboard = _welcome_keyboard(channels)
                try:
                    await client.send_message(
                        message.chat.id,
                        text,
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.error("Failed to send fsub welcome: %s", e)

        # Stop normal welcome from also firing when fsub is active
        message.stop_propagation()

    # ── Callback: "✅ I've Joined" ────────────────────────────
    @app.on_callback_query(filters.regex(r"^fsub_verify:"))
    async def fsub_verify(client, query: CallbackQuery):
        parts = query.data.split(":")
        if len(parts) != 3:
            return await query.answer("Invalid request.", show_alert=True)

        chat_id = int(parts[1])
        target_user_id = int(parts[2])

        # Only the target user can press this button
        if query.from_user.id != target_user_id:
            return await query.answer(
                "❌ This button is not for you.", show_alert=True
            )

        channels = await db.get_fsub_channels(chat_id)
        if not channels:
            return await query.answer("Force-sub is no longer active.", show_alert=True)

        unjoined = await _get_unjoined(client, target_user_id, channels)

        if unjoined:
            labels = ", ".join(ch["label"] for ch in unjoined)
            return await query.answer(
                f"❌ You haven't joined: {labels}\nPlease join and try again.",
                show_alert=True,
            )

        # All joined — unmute the user
        try:
            await client.restrict_chat_member(
                chat_id,
                target_user_id,
                FULL_PERMISSIONS,
            )
        except Exception as e:
            logger.warning("Could not unmute user %s: %s", target_user_id, e)

        # Update the notice message to show success
        try:
            user = query.from_user
            welcome_text = await db.get_welcome_message(chat_id)
            fsub_text = await db.get_fsub_message(chat_id) or DEFAULT_FSUB_MSG
            final_text = welcome_text or fsub_text

            try:
                chat = await client.get_chat(chat_id)
                chat_title = chat.title or ""
            except Exception:
                chat_title = ""

            text = _format_text(final_text, user, chat_title)
            keyboard = _welcome_keyboard(channels)

            await query.message.edit_text(
                text,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning("Could not edit fsub notice: %s", e)

        await query.answer("✅ Verified! You can now chat.", show_alert=False)
