# ============================================================
# Force Subscribe System — DB Layer
# plugin/force_sub/db_force_sub.py
# ============================================================

import motor.motor_asyncio
from config import MONGO_URI, DB_NAME

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]


async def set_force_sub(chat_id: int, enabled: bool, channels: list):
    """Save full force-sub config for a chat."""
    await db.force_sub.update_one(
        {"chat_id": chat_id},
        {
            "$set": {
                "enabled": enabled,
                "channels": channels,
            }
        },
        upsert=True,
    )


async def get_force_sub(chat_id: int) -> dict:
    """
    Returns force-sub config dict for a chat.
    Keys: enabled (bool), channels (list)
    Returns default (disabled) if not found.
    """
    data = await db.force_sub.find_one({"chat_id": chat_id})
    if data:
        return {
            "enabled": data.get("enabled", False),
            "channels": data.get("channels", []),
        }
    return {"enabled": False, "channels": []}


async def enable_force_sub(chat_id: int):
    """Enable force-sub for a chat (keeps existing channels)."""
    await db.force_sub.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": True}},
        upsert=True,
    )


async def disable_force_sub(chat_id: int):
    """Disable force-sub for a chat (keeps existing channels)."""
    await db.force_sub.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": False}},
        upsert=True,
    )


async def add_force_sub_channel(chat_id: int, channel: str):
    """Add a channel to the force-sub list (no duplicates)."""
    await db.force_sub.update_one(
        {"chat_id": chat_id},
        {"$addToSet": {"channels": channel}},
        upsert=True,
    )


async def remove_force_sub_channel(chat_id: int, channel: str):
    """Remove a channel from the force-sub list."""
    await db.force_sub.update_one(
        {"chat_id": chat_id},
        {"$pull": {"channels": channel}},
    )
    


async def has_force_sub_notice(chat_id: int, user_id: int) -> bool:
    """True if this user already received the force-sub join request in this chat."""
    data = await db.force_sub_notice.find_one({"chat_id": chat_id, "user_id": user_id})
    return bool(data)


async def mark_force_sub_notice(chat_id: int, user_id: int):
    """Mark that the force-sub join request was already sent once."""
    await db.force_sub_notice.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"chat_id": chat_id, "user_id": user_id}},
        upsert=True,
    )


async def clear_force_sub_notice(chat_id: int, user_id: int):
    """Allow future notice again after user has joined all required channels."""
    await db.force_sub_notice.delete_one({"chat_id": chat_id, "user_id": user_id})


# ── Custom force-sub message ────────────────────────────────

async def set_force_sub_message(chat_id: int, text: str | None):
    """Save a custom force-sub message template for a chat (or clear it with None)."""
    if text:
        await db.force_sub.update_one(
            {"chat_id": chat_id},
            {"$set": {"message": text}},
            upsert=True,
        )
    else:
        await db.force_sub.update_one(
            {"chat_id": chat_id},
            {"$unset": {"message": ""}},
            upsert=True,
        )


async def get_force_sub_message(chat_id: int) -> str | None:
    """Return the custom force-sub message template for a chat, or None if not set."""
    data = await db.force_sub.find_one({"chat_id": chat_id})
    if data:
        return data.get("message")
    return None
