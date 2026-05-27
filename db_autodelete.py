# ============================================================
# Group Manager Bot — Auto Delete DB Layer
# Add these functions into your existing db.py
# ============================================================

# NOTE: This file is a standalone snippet.
# Paste the contents into your existing db.py,
# or import from here: from db_autodelete import *

import motor.motor_asyncio
from config import MONGO_URI, DB_NAME

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]


# ==========================================================
# 🗑️ Auto Delete System
# ==========================================================

async def set_autodelete(chat_id: int, mode: str, seconds: int, enabled: bool = True):
    """
    Save auto-delete config for a chat.

    Args:
        chat_id  : Telegram chat ID (int)
        mode     : 'messages' | 'media' | 'all'
        seconds  : delete after N seconds (0 = disabled)
        enabled  : master on/off switch
    """
    await db.autodelete.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "enabled": enabled,
                "mode": mode,
                "seconds": seconds,
            }
        },
        upsert=True,
    )


async def get_autodelete(chat_id: int) -> dict:
    """
    Returns the autodelete config dict for a chat.
    Keys: enabled (bool), mode (str), seconds (int)
    Returns default (disabled) if not found.
    """
    data = await db.autodelete.find_one({"chat_id": chat_id})
    if data:
        return {
            "enabled": data.get("enabled", False),
            "mode": data.get("mode", "all"),
            "seconds": data.get("seconds", 0),
        }
    return {"enabled": False, "mode": "all", "seconds": 0}


async def disable_autodelete(chat_id: int):
    """Turn off auto-delete for a chat (keeps other settings)."""
    await db.autodelete.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": False}},
        upsert=True,
    )


async def delete_autodelete_config(chat_id: int):
    """Fully remove autodelete config for a chat."""
    await db.autodelete.delete_one({"chat_id": chat_id})
