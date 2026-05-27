from pyrogram import filters

LOCKED_URL = set()


def has_url(message):
    text = message.text or message.caption or ""

    if "http://" in text or "https://" in text or "t.me/" in text or "telegram.me/" in text:
        return True

    if message.entities:
        for entity in message.entities:
            if entity.type in ("url", "text_link", "mention"):
                return True

    if message.caption_entities:
        for entity in message.caption_entities:
            if entity.type in ("url", "text_link", "mention"):
                return True

    return False


def register_lock_url(app):

    @app.on_message(filters.command("lock") & filters.group, group=-60)
    async def lock_url_cmd(client, message):
        if len(message.command) > 1 and message.command[1].lower() == "url":
            LOCKED_URL.add(message.chat.id)
            await message.reply_text("🔒 Locked url.")
            message.stop_propagation()

    @app.on_message(filters.command("unlock") & filters.group, group=-60)
    async def unlock_url_cmd(client, message):
        if len(message.command) > 1 and message.command[1].lower() == "url":
            LOCKED_URL.discard(message.chat.id)
            await message.reply_text("🔓 Unlocked url.")
            message.stop_propagation()

    @app.on_message(filters.group, group=-120)
    async def delete_locked_url(client, message):
        if message.chat.id not in LOCKED_URL:
            return

        if has_url(message):
            try:
                await message.delete()
            except Exception as e:
                print(f"URL delete failed: {e}")
