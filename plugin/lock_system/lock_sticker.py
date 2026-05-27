from pyrogram import filters

LOCKED_STICKER = set()


def register_lock_sticker(app):

    @app.on_message(filters.command("lock") & filters.group, group=-50)
    async def lock_sticker_cmd(client, message):
        if len(message.command) > 1 and message.command[1].lower() == "sticker":
            LOCKED_STICKER.add(message.chat.id)
            await message.reply_text("🔒 Locked sticker.")
            message.stop_propagation()

    @app.on_message(filters.command("unlock") & filters.group, group=-50)
    async def unlock_sticker_cmd(client, message):
        if len(message.command) > 1 and message.command[1].lower() == "sticker":
            LOCKED_STICKER.discard(message.chat.id)
            await message.reply_text("🔓 Unlocked sticker.")
            message.stop_propagation()

    @app.on_message(filters.sticker & filters.group, group=-100)
    async def delete_locked_sticker(client, message):
        if message.chat.id not in LOCKED_STICKER:
            return

        try:
            await message.delete()
        except Exception as e:
            print(f"Sticker delete failed: {e}")
