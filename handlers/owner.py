# ============================================================
# Owner-only commands: /update, /upgrade, /botinfo
# ============================================================

import asyncio
import logging
import platform
import subprocess
import sys
import time

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from config import OWNER_ID, SUDO_USERS

logger = logging.getLogger(__name__)

_START_TIME = time.time()


def _is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in SUDO_USERS


def _uptime() -> str:
    elapsed = int(time.time() - _START_TIME)
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def _last_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--pretty=%h %s"],
            capture_output=True, text=True, timeout=5,
            cwd="/home/runner/workspace/bot",
        )
        return result.stdout.strip() or "N/A"
    except Exception:
        return "N/A"


def register_owner_handlers(app: Client):

    @app.on_message(filters.command("botinfo"))
    async def cmd_botinfo(client: Client, message: Message):
        if not _is_owner(message.from_user.id):
            return await message.reply_text("ᴏᴡɴᴇʀ ᴏɴʟʏ.")

        try:
            import pyrogram
            pyrogram_ver = pyrogram.__version__
        except Exception:
            pyrogram_ver = "unknown"

        commit = _last_git_commit()

        await message.reply_text(
            "ʙᴏᴛ ɪɴꜰᴏ\n\n"
            f"ᴜᴘᴛɪᴍᴇ : <code>{_uptime()}</code>\n"
            f"ᴘʏᴛʜᴏɴ : <code>{platform.python_version()}</code>\n"
            f"ᴘʏʀᴏɢʀᴀᴍ : <code>{pyrogram_ver}</code>\n"
            f"ᴏꜱ : <code>{platform.system()} {platform.release()}</code>\n\n"
            f"ʟᴀꜱᴛ ᴄᴏᴍᴍɪᴛ : <code>{commit}</code>",
            parse_mode=ParseMode.HTML,
        )

    @app.on_message(filters.command("update"))
    async def cmd_update(client: Client, message: Message):
        if not _is_owner(message.from_user.id):
            return await message.reply_text("ᴏᴡɴᴇʀ ᴏɴʟʏ.")

        msg = await message.reply_text("ʀᴜɴɴɪɴɢ git pull...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                capture_output=True, text=True, timeout=30,
                cwd="/home/runner/workspace/bot",
            )
            output = (result.stdout + result.stderr).strip() or "No output."
            await msg.edit_text(
                "git pull ᴅᴏɴᴇ\n\n"
                f"<pre>{output[:3000]}</pre>\n\n"
                "ʀᴇꜱᴛᴀʀᴛɪɴɢ...",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await msg.edit_text(f"git pull ꜰᴀɪʟᴇᴅ\n\n<code>{e}</code>", parse_mode=ParseMode.HTML)
            return

        await asyncio.sleep(2)
        logger.info("Owner triggered /update — restarting.")
        sys.exit(0)

    @app.on_message(filters.command("upgrade"))
    async def cmd_upgrade(client: Client, message: Message):
        if not _is_owner(message.from_user.id):
            return await message.reply_text("ᴏᴡɴᴇʀ ᴏɴʟʏ.")

        msg = await message.reply_text("ʀᴜɴɴɪɴɢ pip install...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                capture_output=True, text=True, timeout=120,
                cwd="/home/runner/workspace/bot",
            )
            output = (result.stdout + result.stderr).strip() or "ᴀʟʟ ᴘᴀᴄᴋᴀɢᴇꜱ ᴜᴘ ᴛᴏ ᴅᴀᴛᴇ."
            await msg.edit_text(
                "pip install ᴅᴏɴᴇ\n\n"
                f"<pre>{output[:3000]}</pre>\n\n"
                "ʀᴇꜱᴛᴀʀᴛɪɴɢ...",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            await msg.edit_text(f"pip install ꜰᴀɪʟᴇᴅ\n\n<code>{e}</code>", parse_mode=ParseMode.HTML)
            return

        await asyncio.sleep(2)
        logger.info("Owner triggered /upgrade — restarting.")
        sys.exit(0)
