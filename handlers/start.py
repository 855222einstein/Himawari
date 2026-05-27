# ============================================================
# Group Manager Bot - Start/Help handlers
# ============================================================

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import db
import logging

logger = logging.getLogger(__name__)

NEWS_CHANNEL = "https://t.me/shinchan_update"


def register_handlers(app: Client):

    async def get_bot_name(client: Client) -> str:
        """Always use current Telegram bot name, so if name changes to Leo, message says Leo."""
        try:
            me = await client.get_me()
            return me.first_name or "this bot"
        except Exception:
            return "this bot"

    async def send_start_menu(client: Client, message):
        bot_name = await get_bot_name(client)
        me = await client.get_me()
        bot_username = me.username

        text = f"""Hey there! My name is {bot_name} - I'm here to help you manage your groups! Use /help to find out how to use me to my full potential.

Join my <a href=\"{NEWS_CHANNEL}\">news channel</a> to get information on all the latest updates.

Check /privacy to view the privacy policy, and interact with your data."""

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "ᴀᴅᴅ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ",
                    url=f"https://t.me/{bot_username}?startgroup=true"
                )
            ]
        ])

        await message.reply_text(
            text=text,
            reply_markup=buttons,
            disable_web_page_preview=True,
            quote=True
        )

    # /start command: text only, no image, only Add me to your Group button
    @app.on_message(filters.private & filters.command("start"), group=-100)
    async def start_command(client, message):
        user = message.from_user
        try:
            await send_start_menu(client, message)
            try:
                if user:
                    await db.add_user(user.id, user.first_name)
            except Exception as exc:
                logger.warning("Failed to save /start user %s: %s", user.id if user else None, exc)
        except Exception as exc:
            logger.exception("/start failed: %s", exc)
            bot_name = await get_bot_name(client)
            await message.reply_text(
                f"Hey there! My name is {bot_name} - I'm here to help you manage your groups! Use /help to find out how to use me to my full potential.",
                quote=True
            )

    # /help command stays simple and text-only
    @app.on_message(filters.private & filters.command("help"), group=-90)
    async def help_command(client, message):
        await message.reply_text(
            "Use me in groups to manage welcome, locks and moderation commands.",
            quote=True
        )
