# ============================================================
# plugin/service_delete_system/commands.py
#
# Admin commands to toggle service-message auto-delete.
#
# /service_delete_on   — enable for this group
# /service_delete_off  — disable for this group
# ============================================================

import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatMemberStatus

from db_service_delete import set_service_delete, get_service_delete

logger = logging.getLogger(__name__)


# ── Helper: admin check ─────────────────────────────────────

async def _is_admin(client: Client, chat_id: int, user_id: int) -> bool:
    """Returns True if user is an admin or owner of the chat."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in (
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        )
    except Exception:
        return False


# ── /service_delete_on ──────────────────────────────────────

async def cmd_service_delete_on(client: Client, message: Message) -> None:
    """
    Admin command: enable auto-deletion of join/leave service messages.
    Bot must have 'Delete Messages' admin permission to actually delete.
    """
    # Groups only
    if message.chat.type.value == "private":
        await message.reply_text("⚠️ This command works in groups only.")
        return

    # Admin-only gate
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🚫 Only admins can use this command.")
        return

    await set_service_delete(message.chat.id, enabled=True)
    logger.info("ServiceDelete ENABLED  chat=%s by user=%s", message.chat.id, message.from_user.id)

    await message.reply_text(
        "✅ ꜱᴇʀᴠɪᴄᴇ ᴍᴇꜱꜱᴀɢᴇ\n"
        "ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ : ᴏɴ\n\n"
        "ᴊᴏɪɴ ᴀɴᴅ ʟᴇᴀᴠᴇ\n"
        "ꜱᴇʀᴠɪᴄᴇ ᴍᴇꜱꜱᴀɢᴇꜱ\n"
        "ᴡɪʟʟ ɴᴏᴡ ʙᴇ\n"
        "ᴅᴇʟᴇᴛᴇᴅ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ.\n\n"
        "• ɴᴇᴡ_ᴄʜᴀᴛ_ᴍᴇᴍʙᴇʀꜱ\n"
        "• ʟᴇꜰᴛ_ᴄʜᴀᴛ_ᴍᴇᴍʙᴇʀ\n\n"
        "ᴍᴀᴋᴇ ꜱᴜʀᴇ ʙᴏᴛ ʜᴀꜱ\n"
        "ᴅᴇʟᴇᴛᴇ ᴍᴇꜱꜱᴀɢᴇꜱ ᴘᴇʀᴍɪꜱꜱɪᴏɴ."
    )


# ── /service_delete_off ─────────────────────────────────────

async def cmd_service_delete_off(client: Client, message: Message) -> None:
    """
    Admin command: disable auto-deletion of join/leave service messages.
    """
    # Groups only
    if message.chat.type.value == "private":
        await message.reply_text("⚠️ This command works in groups only.")
        return

    # Admin-only gate
    if not await _is_admin(client, message.chat.id, message.from_user.id):
        await message.reply_text("🚫 Only admins can use this command.")
        return

    await set_service_delete(message.chat.id, enabled=False)
    logger.info("ServiceDelete DISABLED chat=%s by user=%s", message.chat.id, message.from_user.id)

    await message.reply_text(
        "🔴 ꜱᴇʀᴠɪᴄᴇ ᴍᴇꜱꜱᴀɢᴇ\n"
        "ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇ : ᴏꜰꜰ\n\n"
        "ᴊᴏɪɴ ᴀɴᴅ ʟᴇᴀᴠᴇ\n"
        "ᴍᴇꜱꜱᴀɢᴇꜱ ᴡɪʟʟ\n"
        "ɴᴏ ʟᴏɴɢᴇʀ ʙᴇ\n"
        "ᴀᴜᴛᴏ-ᴅᴇʟᴇᴛᴇᴅ.\n\n"
        "ᴜꜱᴇ /service_delete_on\n"
        "ᴛᴏ ʀᴇ-ᴇɴᴀʙʟᴇ."
    )


# ── Registration helper ─────────────────────────────────────

def register_service_delete_commands(app: Client) -> None:
    """Bind command handlers. Called from handler.py."""
    app.on_message(filters.command("service_delete_on"))(cmd_service_delete_on)
    app.on_message(filters.command("service_delete_off"))(cmd_service_delete_off)
    logger.info("✅ ServiceDelete commands registered (/service_delete_on | off).")
    
