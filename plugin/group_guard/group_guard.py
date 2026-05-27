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
            InlineKeyboardButton("✅ Accept", callback_data=f"gg_accept:{group_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"gg_reject:{group_id}"),
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

            # Mark as pending in DB
            await db.set_group_approval(group_id, "pending")

            # Notify the group that approval is needed
            await _notify_group(
                client, group_id,
                "ᴛʜɪꜱ ɢʀᴏᴜᴘ ɪꜱ ᴜɴᴅᴇʀ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ\n\n"
                "━━━━━━━━━━━━━━━━\n\n"
                "ʙᴏᴛ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀʀᴇ ᴄᴜʀʀᴇɴᴛʟʏ ᴅɪꜱᴀʙʟᴇᴅ.\n\n"
                "ᴀᴘᴘʀᴏᴠᴀʟ ɪꜱ ʀᴇQᴜɪʀᴇᴅ ʙᴇꜰᴏʀᴇ\n"
                "ᴜꜱɪɴɢ ᴀɴʏ ꜰᴇᴀᴛᴜʀᴇꜱ.\n\n"
                "━━━━━━━━━━━━━━━━"
            )

            # Build log channel message
            adder_name = added_by.first_name if added_by else "Unknown"
            adder_id   = added_by.id         if added_by else "N/A"
            text = (
                "🚨 <b>Bot Added To New Group</b>\n\n"
                f"👥 <b>Group:</b> {group_title}\n"
                f"🆔 <b>Group ID:</b> <code>{group_id}</code>\n\n"
                f"👤 <b>Added By:</b> {adder_name}\n"
                f"🆔 <b>User ID:</b> <code>{adder_id}</code>\n\n"
                "⏳ <b>Status:</b> Pending Approval\n\n"
                "Accept or Reject this group?"
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
            return await query.answer("⛔ You are not authorised.", show_alert=True)

        group_id = int(query.data.split(":")[1])
        await db.set_group_approval(group_id, "approved", approved_by=query.from_user.id)

        try:
            chat = await client.get_chat(group_id)
            group_title = chat.title or str(group_id)
        except Exception:
            group_title = str(group_id)

        await query.message.edit_text(
            f"✅ <b>Group Approved</b>\n\n"
            f"👥 <b>Group:</b> {group_title}\n"
            f"🆔 <code>{group_id}</code>\n\n"
            f"👤 Approved by: {query.from_user.mention}",
        )
        await query.answer("✅ Group approved!")

        # Notify the group
        await _notify_group(
            client, group_id,
            "ɢʀᴏᴜᴘ ᴠᴇʀɪꜰɪᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "ᴀʟʟ ᴄᴏᴍᴍᴀɴᴅꜱ ᴀɴᴅ ꜰᴇᴀᴛᴜʀᴇꜱ\n"
            "ᴀʀᴇ ɴᴏᴡ ᴀᴄᴛɪᴠᴇ.\n\n"
            "ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴄʜᴏᴏꜱɪɴɢ ᴛʜɪꜱ ʙᴏᴛ.\n\n"
            "━━━━━━━━━━━━━━━━"
        )

    # ── 3. Reject callback ────────────────────────────────────
    @app.on_callback_query(filters.regex(r"^gg_reject:"))
    async def reject_group(client, query):
        if not _is_sudo(query.from_user.id):
            return await query.answer("⛔ You are not authorised.", show_alert=True)

        group_id = int(query.data.split(":")[1])

        # Mark rejected and clean up DB data
        await db.set_group_approval(group_id, "rejected")
        await db.clear_group_data(group_id)

        # Notify group before leaving
        await _notify_group(
            client, group_id,
            "ɢʀᴏᴜᴘ ᴀᴄᴄᴇꜱꜱ ᴅᴇɴɪᴇᴅ\n\n"
            "━━━━━━━━━━━━━━━━\n\n"
            "ᴛʜɪꜱ ɢʀᴏᴜᴘ ᴅᴏᴇꜱ ɴᴏᴛ ᴍᴇᴇᴛ\n"
            "ᴛʜᴇ ʀᴇQᴜɪʀᴇᴅ ᴄᴏɴᴅɪᴛɪᴏɴꜱ.\n\n"
            "ʙᴏᴛ ꜱᴇʀᴠɪᴄᴇꜱ ʜᴀᴠᴇ ʙᴇᴇɴ ᴅɪꜱᴀʙʟᴇᴅ.\n\n"
            "━━━━━━━━━━━━━━━━"
        )

        # Leave the group
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

        status_line = "Bot left the group." if leave_ok else "⚠️ Could not leave — may have already left."
        await query.message.edit_text(
            f"❌ <b>Group Rejected</b>\n\n"
            f"👥 <b>Group:</b> {group_title}\n"
            f"🆔 <code>{group_id}</code>\n\n"
            f"👤 Rejected by: {query.from_user.mention}\n"
            f"📌 {status_line}",
        )
        await query.answer("❌ Group rejected and bot left.")

    # ── 4. Block ALL group commands until approved ─────────────
    @app.on_message(filters.group & filters.command([""]), group=-199)
    async def _placeholder(_c, _m):
        # Real blocking is in the middleware below (group=-198 handler)
        pass

    @app.on_message(filters.group, group=-198)
    async def command_gate(client, message):
        """
        Silently drop every message/command in unapproved groups.
        group=-198 fires before all normal handlers (group 0+).
        """
        if not message.from_user:
            return

        chat_id = message.chat.id
        approved = await db.is_group_approved(chat_id)
        status   = await db.get_group_approval(chat_id)

        if approved:
            return  # Let it pass through to normal handlers

        # Group is pending or rejected — block commands
        if message.text and message.text.startswith("/"):
            cmd = message.text.split()[0].split("@")[0]
            # Allow a small whitelist so the owner can still interact
            whitelist = {"/start", "/ping", "/help"}
            if cmd.lower() not in whitelist:
                if status == "rejected":
                    await message.reply_text(
                        "🚫 This group has been **rejected**. The bot cannot be used here."
                    )
                else:
                    await message.reply_text(
                        "⏳ This group is **pending approval**.\n"
                        "Commands are disabled until the bot owner approves this group."
                    )
                message.stop_propagation()
