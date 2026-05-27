# ============================================================
# Welcome System — with group approval gate
# ============================================================
from pyrogram import filters
import db
from plugin.group_guard.group_guard import group_is_approved


def register_welcome_system(app):

    @app.on_message(filters.command("welcome") & filters.group)
    async def toggle_welcome(client, message):
        if not await group_is_approved(message.chat.id):
            return  # silently ignore unapproved groups

        member = await client.get_chat_member(
            message.chat.id, message.from_user.id
        )
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Only admins can use this command.")

        if len(message.command) < 2:
            return await message.reply_text("Usage:\n/welcome on\n/welcome off")

        option = message.command[1].lower()

        if option == "on":
            await db.set_welcome_status(message.chat.id, True)
            return await message.reply_text("✅ Welcome enabled.")

        elif option == "off":
            await db.set_welcome_status(message.chat.id, False)
            return await message.reply_text("❌ Welcome disabled.")

    @app.on_message(filters.command("setwelcome") & filters.group)
    async def set_welcome(client, message):
        if not await group_is_approved(message.chat.id):
            return

        member = await client.get_chat_member(
            message.chat.id, message.from_user.id
        )
        if not (member.privileges and member.privileges.can_manage_chat):
            return await message.reply_text("Only admins can use this command.")

        text = message.text.split(None, 1)
        if len(text) < 2:
            return await message.reply_text(
                "Usage:\n/setwelcome Welcome {first_name}"
            )

        await db.set_welcome_message(message.chat.id, text[1])
        await message.reply_text("✅ Welcome message updated.")

    @app.on_message(filters.new_chat_members)
    async def welcome_new_member(client, message):
        if not await group_is_approved(message.chat.id):
            return  # silently skip unapproved groups

        enabled = await db.get_welcome_status(message.chat.id)
        if not enabled:
            return

        template = await db.get_welcome_message(message.chat.id) or \
                   "Hello {first_name}, welcome to {title}!"

        for user in message.new_chat_members:
            # Don't welcome the bot itself
            me = await client.get_me()
            if user.id == me.id:
                continue

            text = template.format(
                first_name=user.first_name,
                username=user.username or "NoUsername",
                id=user.id,
                mention=user.mention,
                title=message.chat.title,
            )
            await message.reply_text(text)
