# ============================================================
# Group Manager Bot / NomadeHelpBot
# ============================================================

import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URI = os.getenv("MONGO_URI", "")
DB_NAME = os.getenv("DB_NAME", "Cluster0")

OWNER_ID = int(os.getenv("OWNER_ID", 0))
BOT_USERNAME = os.getenv("BOT_USERNAME", "NomadeHelpBot").lstrip("@")

SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/LearningBotsCommunity")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL", "https://t.me/Learning_Bots")
START_IMAGE = os.getenv("START_IMAGE", "https://files.catbox.moe/o5eekb.jpg")


def _parse_chat_id(value: str):
    value = (value or "").strip()
    if not value:
        return 0
    # Supports both -100xxxxxxxxxx numeric ids and @public_channel usernames.
    if value.startswith("@"):
        return value
    try:
        return int(value)
    except ValueError:
        return value


LOG_CHAT_ID = _parse_chat_id(os.getenv("LOG_CHAT_ID", ""))
SUDO_USERS = [int(x) for x in os.getenv("SUDO_USERS", str(OWNER_ID)).replace(" ", "").split(",") if x]
