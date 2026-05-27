from pyrogram import filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import ChatPermissions
import db
from plugin.group_guard.group_guard import group_is_approved

VALID_LOCKS = ["url", "sticker", "media", "username", "forward"]


async def can_use_lock(client, chat_id, user_id):
    member = await client.get_chat_member(chat_id, user_id)
    return member.status in [
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR
    ]


async def get_current_permissions(client, chat_id):
    """Current group permissions fetch karo"""
    chat = await client.get_chat(chat_id)
    perms = chat.permissions
    return perms


def register_lock_system(app):

    @app.on_message(filters.command("lock") & filters.group)
    async def lock_cmd(client, message):

        if not message.from_user:
            return

        if not await group_is_approved(message.chat.id):
            return await message.reply_text("⏳ This group is **pending approval**. Commands are disabled.")

        if not await can_use_lock(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admins can use this command.")

        if len(message.command) < 2:
            return await message.reply_text(
                "⚠️ Available: url, sticker, media, username, forward, all"
            )

        lock_type = message.command[1].lower()

        # ── LOCK ALL ──────────────────────────────────────────
        if lock_type == "all":
            current = await get_current_permissions(client, message.chat.id)

            # Already fully locked check
            if not current.can_send_messages:
                return await message.reply_text("ℹ️ Group already fully locked.")

            try:
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(can_send_messages=False)
                )
                return await message.reply_text("🔒 Group fully locked.")
            except Exception as e:
                return await message.reply_text(f"❌ Failed to lock group:\n{e}")

        # ── OTHER LOCKS ───────────────────────────────────────
        if lock_type not in VALID_LOCKS:
            return await message.reply_text(
                "⚠️ Available: url, sticker, media, username, forward, all"
            )

        current = await get_current_permissions(client, message.chat.id)

        try:
            if lock_type == "media":
                if not current.can_send_media_messages:
                    return await message.reply_text("ℹ️ Media already locked.")
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(
                        can_send_messages=current.can_send_messages,
                        can_send_media_messages=False,
                        can_send_other_messages=current.can_send_other_messages,
                        can_add_web_page_previews=current.can_add_web_page_previews,
                        can_send_polls=current.can_send_polls,
                        can_invite_users=current.can_invite_users,
                    )
                )

            elif lock_type == "sticker":
                if not current.can_send_other_messages:
                    return await message.reply_text("ℹ️ Stickers already locked.")
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(
                        can_send_messages=current.can_send_messages,
                        can_send_media_messages=current.can_send_media_messages,
                        can_send_other_messages=False,
                        can_add_web_page_previews=current.can_add_web_page_previews,
                        can_send_polls=current.can_send_polls,
                        can_invite_users=current.can_invite_users,
                    )
                )

            elif lock_type in ["url", "forward", "username"]:
                # These are handled by lock_url / group_guard plugins
                return await message.reply_text(f"🔒 Locked {lock_type}.")

            return await message.reply_text(f"🔒 Locked {lock_type}.")

        except Exception as e:
            return await message.reply_text(f"❌ Failed to lock {lock_type}:\n{e}")


    @app.on_message(filters.command("unlock") & filters.group)
    async def unlock_cmd(client, message):

        if not message.from_user:
            return

        if not await group_is_approved(message.chat.id):
            return await message.reply_text("⏳ This group is **pending approval**. Commands are disabled.")

        if not await can_use_lock(client, message.chat.id, message.from_user.id):
            return await message.reply_text("❌ Only admins can use this command.")

        if len(message.command) < 2:
            return await message.reply_text(
                "⚠️ Available: url, sticker, media, username, forward, all"
            )

        lock_type = message.command[1].lower()

        # ── UNLOCK ALL ────────────────────────────────────────
        if lock_type == "all":
            current = await get_current_permissions(client, message.chat.id)

            # Already fully unlocked check
            if (
                current.can_send_messages
                and current.can_send_media_messages
                and current.can_send_other_messages
                and current.can_add_web_page_previews
            ):
                return await message.reply_text("ℹ️ Group already fully unlocked.")

            try:
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(
                        can_send_messages=True,
                        can_send_media_messages=True,
                        can_send_other_messages=True,
                        can_add_web_page_previews=True,
                        can_send_polls=True,
                        can_invite_users=True,
                    ),
                )
                return await message.reply_text("🔓 Group fully unlocked.")
            except Exception as e:
                return await message.reply_text(f"❌ Failed to unlock group:\n{e}")

        # ── OTHER UNLOCKS ─────────────────────────────────────
        if lock_type not in VALID_LOCKS:
            return await message.reply_text(
                "⚠️ Available: url, sticker, media, username, forward, all"
            )

        current = await get_current_permissions(client, message.chat.id)

        try:
            if lock_type == "media":
                if current.can_send_media_messages:
                    return await message.reply_text("ℹ️ Media already unlocked.")
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(
                        can_send_messages=current.can_send_messages,
                        can_send_media_messages=True,
                        can_send_other_messages=current.can_send_other_messages,
                        can_add_web_page_previews=current.can_add_web_page_previews,
                        can_send_polls=current.can_send_polls,
                        can_invite_users=current.can_invite_users,
                    )
                )

            elif lock_type == "sticker":
                if current.can_send_other_messages:
                    return await message.reply_text("ℹ️ Stickers already unlocked.")
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(
                        can_send_messages=current.can_send_messages,
                        can_send_media_messages=current.can_send_media_messages,
                        can_send_other_messages=True,
                        can_add_web_page_previews=current.can_add_web_page_previews,
                        can_send_polls=current.can_send_polls,
                        can_invite_users=current.can_invite_users,
                    )
                )

            elif lock_type in ["url", "forward", "username"]:
                return await message.reply_text(f"🔓 Unlocked {lock_type}.")

            return await message.reply_text(f"🔓 Unlocked {lock_type}.")

        except Exception as e:
            return await message.reply_text(f"❌ Failed to unlock {lock_type}:\n{e}")
