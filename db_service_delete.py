# ============================================================
# Group Manager Bot — Service Delete DB Layer
# db_service_delete.py
#
# Stores per-chat on/off state for auto-deleting
# Telegram join/leave service messages.
# ============================================================

import motor.motor_asyncio
from config import MONGO_URI, DB_NAME

_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
_db = _client[DB_NAME]

# Collection: service_delete
# Schema: { chat_id: int, enabled: bool }


# ── Read ────────────────────────────────────────────────────

async def get_service_delete(chat_id: int) -> bool:
    """
    Returns True if service-message auto-delete is enabled for this chat.
    Defaults to False (opt-in, not opt-out).
    """
    doc = await _db.service_delete.find_one({"chat_id": chat_id})
    if doc:
        return bool(doc.get("enabled", False))
    return False


# ── Write ───────────────────────────────────────────────────

async def set_service_delete(chat_id: int, enabled: bool) -> None:
    """Enable or disable service-message auto-delete for a chat."""
    await _db.service_delete.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": enabled}},
        upsert=True,
    )


# ── Cleanup (optional, called by clear_group_data) ──────────

async def delete_service_delete_config(chat_id: int) -> None:
    """Remove config entirely when a group is cleaned up."""
    await _db.service_delete.delete_one({"chat_id": chat_id})
  
