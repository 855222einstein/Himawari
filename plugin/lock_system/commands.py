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
    chat = await client.get_chat(chat_id)
    return chat.permissions


def register_lock_system(app):

    @app.on_message(filters.command("lock") & filters.group)
    async def lock_cmd(client, message):

        if not message.from_user:
            return

        if not await group_is_approved(message.chat.id):
            return await message.reply_text("ᴛʜɪꜱ ɢʀᴏᴜᴘ ɪꜱ ᴘᴇɴᴅɪɴɢ ᴀᴘᴘʀᴏᴠᴀʟ.")

        if not await can_use_lock(client, message.chat.id, message.from_user.id):
            return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

        if len(message.command) < 2:
            return await message.reply_text(
                "ᴀᴠᴀɪʟᴀʙʟᴇ : url  sticker  media  username  forward  all"
            )

        lock_type = message.command[1].lower()

        if lock_type == "all":
            current = await get_current_permissions(client, message.chat.id)
            if not current.can_send_messages:
                return await message.reply_text("ɢʀᴏᴜᴘ ᴀʟʀᴇᴀᴅʏ ꜰᴜʟʟʏ ʟᴏᴄᴋᴇᴅ.")
            try:
                await client.set_chat_permissions(
                    message.chat.id,
                    ChatPermissions(can_send_messages=False)
                )
                return await message.reply_text("ɢʀᴏᴜᴘ ꜰᴜʟʟʏ ʟᴏᴄᴋᴇᴅ.")
            except Exception as e:
                return await message.reply_text(f"ꜰᴀɪʟᴇᴅ ᴛᴏ ʟᴏᴄᴋ ɢʀᴏᴜᴘ.\n{e}")

        if lock_type not in VALID_LOCKS:
            return await message.reply_text(
                "ᴀᴠᴀɪʟᴀʙʟᴇ : url  sticker  media  username  forward  all"
            )

        current = await get_current_permissions(client, message.chat.id)

        try:
            if lock_type == "media":
                if not current.can_send_media_messages:
                    return await message.reply_text("ᴍᴇᴅɪᴀ ᴀʟʀᴇᴀᴅʏ ʟᴏᴄᴋᴇᴅ.")
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
                    return await message.reply_text("ꜱᴛɪᴄᴋᴇʀꜱ ᴀʟʀᴇᴀᴅʏ ʟᴏᴄᴋᴇᴅ.")
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
                return await message.reply_text(f"ʟᴏᴄᴋᴇᴅ : {lock_type}")

            return await message.reply_text(f"ʟᴏᴄᴋᴇᴅ : {lock_type}")

        except Exception as e:
            return await message.reply_text(f"ꜰᴀɪʟᴇᴅ ᴛᴏ ʟᴏᴄᴋ {lock_type}.\n{e}")


    @app.on_message(filters.command("unlock") & filters.group)
    async def unlock_cmd(client, message):

        if not message.from_user:
            return

        if not await group_is_approved(message.chat.id):
            return await message.reply_text("ᴛʜɪꜱ ɢʀᴏᴜᴘ ɪꜱ ᴘᴇɴᴅɪɴɢ ᴀᴘᴘʀᴏᴠᴀʟ.")

        if not await can_use_lock(client, message.chat.id, message.from_user.id):
            return await message.reply_text("ᴀᴅᴍɪɴꜱ ᴏɴʟʏ.")

        if len(message.command) < 2:
            return await message.reply_text(
                "ᴀᴠᴀɪʟᴀʙʟᴇ : url  sticker  media  username  forward  all"
            )

        lock_type = message.command[1].lower()

        if lock_type == "all":
            current = await get_current_permissions(client, message.chat.id)
            if (
                current.can_send_messages
                and current.can_send_media_messages
                and current.can_send_other_messages
                and current.can_add_web_page_previews
            ):
                return await message.reply_text("ɢʀᴏᴜᴘ ᴀʟʀᴇᴀᴅʏ ꜰᴜʟʟʏ ᴜɴʟᴏᴄᴋᴇᴅ.")
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
                return await message.reply_text("ɢʀᴏᴜᴘ ꜰᴜʟʟʏ ᴜɴʟᴏᴄᴋᴇᴅ.")
            except Exception as e:
                return await message.reply_text(f"ꜰᴀɪʟᴇᴅ ᴛᴏ ᴜɴʟᴏᴄᴋ ɢʀᴏᴜᴘ.\n{e}")

        if lock_type not in VALID_LOCKS:
            return await message.reply_text(
                "ᴀᴠᴀɪʟᴀʙʟᴇ : url  sticker  media  username  forward  all"
            )

        current = await get_current_permissions(client, message.chat.id)

        try:
            if lock_type == "media":
                if current.can_send_media_messages:
                    return await message.reply_text("ᴍᴇᴅɪᴀ ᴀʟʀᴇᴀᴅʏ ᴜɴʟᴏᴄᴋᴇᴅ.")
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
                    return await message.reply_text("ꜱᴛɪᴄᴋᴇʀꜱ ᴀʟʀᴇᴀᴅʏ ᴜɴʟᴏᴄᴋᴇᴅ.")
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
                return await message.reply_text(f"ᴜɴʟᴏᴄᴋᴇᴅ : {lock_type}")

            return await message.reply_text(f"ᴜɴʟᴏᴄᴋᴇᴅ : {lock_type}")

        except Exception as e:
            return await message.reply_text(f"ꜰᴀɪʟᴇᴅ ᴛᴏ ᴜɴʟᴏᴄᴋ {lock_type}.\n{e}")
