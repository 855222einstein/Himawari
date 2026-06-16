# ============================================================
# Group Guard — Full Approval System
# ============================================================
# Features:
#   • Bot added to group → log channel gets approval message with buttons
#   • MongoDB stores approval status (pending / approved / rejected)
#   • All commands blocked in group until approved
#   • Reject → bot leaves group + deletes group data
#   • Welcome/features silently disabled for unapproved groups
# ============================================================

import logging
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import LOG_CHAT_ID, SUDO_USERS, OWNER_ID
import db

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────

def _is_sudo(user_id: int) -> bool:
    return user_id in SUDO_USERS or user_id == OWNER_ID


def _approval_buttons(group_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("ᴀᴄᴄᴇᴘᴛ", callback_data=f"gg_accept:{group_id}"),
            InlineKeyboardButton("ʀᴇᴊᴇᴄᴛ", callback_data=f"gg_reject:{group_id}"),
        ]
    ])


async def _notify_group(client, group_id: int, text: str):
    """Send a message to a group, silently ignore errors."""
    try:
        await client.send_message(group_id, text)
    except Exception as e:
        logger.warning("Could not notify group %s: %s", group_id, e)


# ── Public guard used by other handlers ──────────────────────

async def group_is_approved(chat_id: int) -> bool:
    """
    Returns True only when the group has been explicitly approved.
    Import this in other handlers to gate features.
    """
    return await db.is_group_approved(chat_id)


# ── Registration ─────────────────────────────────────────────

def register_group_guard(app):

    # ── 1. Bot added to a group ────────────────────────────────
    @app.on_message(filters.new_chat_members & filters.group, group=-200)
    async def on_bot_added(client, message):
        me = await client.get_me()
        for user in message.new_chat_members:
            if user.id != me.id:
                continue

            group_id    = message.chat.id
            group_title = message.chat.title or str(group_id)
            added_by    = message.from_user

            await db.set_group_approval(group_id, "pending")

            await _notify_group(
                client, group_id,
                "ᴛʜɪꜱ ɢʀᴏᴜᴘ ɪꜱ ᴜɴᴅᴇʀ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ\n\n"
                "ʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ᴄᴜʀʀᴇɴᴛʟʏ ᴅɪꜱᴀʙʟᴇᴅ.\n"
                "ᴀᴘᴘʀᴏᴠᴀʟ ɪꜱ ʀᴇQᴜɪʀᴇᴅ ʙᴇꜰᴏʀᴇ ᴜꜱɪɴɢ ᴀɴʏ ꜰᴇᴀᴛᴜʀᴇꜱ."
            )

            adder_name = added_by.first_name if added_by else "Unknown"
            adder_id   = added_by.id         if added_by else "N/A"
            text = (
                "<b>ɴᴇᴡ ɢʀᴏᴜᴘ</b>\n\n"
                f"<b>ɴᴀᴍᴇ :</b> {group_title}\n"
                f"<b>ɪᴅ :</b> <code>{group_id}</code>\n\n"
                f"<b>ᴀᴅᴅᴇᴅ ʙʏ :</b> {adder_name}\n"
                f"<b>ᴜꜱᴇʀ ɪᴅ :</b> <code>{adder_id}</code>\n\n"
                "<b>ꜱᴛᴀᴛᴜꜱ :</b> ᴘᴇɴᴅɪɴɢ ᴀᴘᴘʀᴏᴠᴀʟ"
            )

            if not LOG_CHAT_ID:
                logger.warning("LOG_CHAT_ID not set — cannot send approval request.")
                return

            try:
                await client.send_message(
                    LOG_CHAT_ID,
                    text,
                    reply_markup=_approval_buttons(group_id),
                )
            except Exception as e:
                logger.error("Failed to send approval request to log channel: %s", e)

    # ── 2. Accept callback ────────────────────────────────────
    @app.on_callback_query(filters.regex(r"^gg_accept:"))
    async def accept_group(client, query):
        if not _is_sudo(query.from_user.id):
            return await query.answer("ɴᴏᴛ ᴀᴜᴛʜᴏʀɪꜱᴇᴅ.", show_alert=True)

        group_id = int(query.data.split(":")[1])
        await db.set_group_approval(group_id, "approved", approved_by=query.from_user.id)

        try:
            chat = await client.get_chat(group_id)
            group_title = chat.title or str(group_id)
        except Exception:
            group_title = str(group_id)

        await query.message.edit_text(
            f"<b>ɢʀᴏᴜᴘ ᴀᴘᴘʀᴏᴠᴇᴅ</b>\n\n"
            f"<b>ɴᴀᴍᴇ :</b> {group_title}\n"
            f"<b>ɪᴅ :</b> <code>{group_id}</code>\n\n"
            f"<b>ʙʏ :</b> {query.from_user.mention}",
        )
        await query.answer("ᴀᴘᴘʀᴏᴠᴇᴅ")

        await _notify_group(
            client, group_id,
            "ɢʀᴏᴜᴘ ᴠᴇʀɪꜰɪᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ\n\n"
            "ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀɴᴅ ꜰᴇᴀᴛᴜʀᴇꜱ ᴀʀᴇ ɴᴏᴡ ᴀᴄᴛɪᴠᴇ."
        )

    # ── 3. Reject callback ────────────────────────────────────
    @app.on_callback_query(filters.regex(r"^gg_reject:"))
    async def reject_group(client, query):
        if not _is_sudo(query.from_user.id):
            return await query.answer("ɴᴏᴛ ᴀᴜᴛʜᴏʀɪꜱᴇᴅ.", show_alert=True)

        group_id = int(query.data.split(":")[1])

        await db.set_group_approval(group_id, "rejected")
        await db.clear_group_data(group_id)

        await _notify_group(
            client, group_id,
            "ɢʀᴏᴜᴘ ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ\n\n"
            "ᴛʜɪꜱ ɢʀᴏᴜᴘ ᴅᴏᴇꜱ ɴᴏᴛ ᴍᴇᴇᴛ ᴛʜᴇ ʀᴇQᴜɪʀᴇᴅ ᴄᴏɴᴅɪᴛɪᴏɴꜱ.\n"
            "ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ᴅɪꜱᴀʙʟᴇᴅ."
        )

        leave_ok = True
        try:
            await client.leave_chat(group_id)
        except Exception as e:
            leave_ok = False
            logger.warning("Could not leave group %s: %s", group_id, e)

        try:
            chat = await client.get_chat(group_id)
            group_title = chat.title or str(group_id)
        except Exception:
            group_title = str(group_id)

        status_line = "ʙᴏᴛ ʟᴇꜰᴛ ᴛʜᴇ ɢʀᴏᴜᴘ." if leave_ok else "ᴄᴏᴜʟᴅ ɴᴏᴛ ʟᴇᴀᴠᴇ — ᴍᴀʏ ʜᴀᴠᴇ ᴀʟʀᴇᴀᴅʏ ʟᴇꜰᴛ."
        await query.message.edit_text(
            f"<b>ɢʀᴏᴜᴘ ʀᴇᴊᴇᴄᴛᴇᴅ</b>\n\n"
            f"<b>ɴᴀᴍᴇ :</b> {group_title}\n"
            f"<b>ɪᴅ :</b> <code>{group_id}</code>\n\n"
            f"<b>ʙʏ :</b> {query.from_user.mention}\n"
            f"{status_line}",
        )
        await query.answer("ʀᴇᴊᴇᴄᴛᴇᴅ")

    # ── 4. Block ALL group commands until approved ─────────────
    @app.on_message(filters.group & filters.command([""]), group=-199)
    async def _placeholder(_c, _m):
        pass

    @app.on_message(filters.group, group=-198)
    async def command_gate(client, message):
        if not message.from_user:
            return

        chat_id = message.chat.id
        approved = await db.is_group_approved(chat_id)
        status   = await db.get_group_approval(chat_id)

        if approved:
            return

        if message.text and message.text.startswith("/"):
            cmd = message.text.split()[0].split("@")[0]
            whitelist = {"/start", "/ping", "/help"}
            if cmd.lower() not in whitelist:
                if status == "rejected":
                    await message.reply_text(
                        "ᴛʜɪꜱ ɢʀᴏᴜᴘ ʜᴀꜱ ʙᴇᴇɴ ʀᴇᴊᴇᴄᴛᴇᴅ.\n"
                        "ᴛʜᴇ ʙᴏᴛ ᴄᴀɴɴᴏᴛ ʙᴇ ᴜꜱᴇᴅ ʜᴇʀᴇ."
                    )
                else:
                    await message.reply_text(
                        "ᴛʜɪꜱ ɢʀᴏᴜᴘ ɪꜱ ᴘᴇɴᴅɪɴɢ ᴀᴘᴘʀᴏᴠᴀʟ.\n"
                        "ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ᴅɪꜱᴀʙʟᴇᴅ ᴜɴᴛɪʟ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ ᴀᴘᴘʀᴏᴠᴇꜱ."
                    )
                message.stop_propagation()
