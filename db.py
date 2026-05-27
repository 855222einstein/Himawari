# ============================================================
# Group Manager Bot
# Author: LearningBotsOfficial (https://github.com/LearningBotsOfficial) 
# Support: https://t.me/LearningBotsCommunity
# Channel: https://t.me/learning_bots
# YouTube: https://youtube.com/@learning_bots
# License: Open-source (keep credits, no resale)
# ============================================================


import motor.motor_asyncio
from config import MONGO_URI, DB_NAME
import logging

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

logging.info("✅ MongoDB initialized")

# ==========================================================
# 🟢 Welcome
# ==========================================================

async def set_welcome_message(chat_id, text: str):
    await db.welcome.update_one(
        {"chat_id": chat_id},
        {"$set": {"message": text}},
        upsert=True
    )

async def get_welcome_message(chat_id):
    data = await db.welcome.find_one({"chat_id": chat_id})
    return data.get("message") if data else None

async def set_welcome_status(chat_id, status: bool):
    await db.welcome.update_one(
        {"chat_id": chat_id},
        {"$set": {"enabled": status}},
        upsert=True
    )

async def get_welcome_status(chat_id) -> bool:
    data = await db.welcome.find_one({"chat_id": chat_id})
    return bool(data.get("enabled", True)) if data else True

# ==========================================================
# 🔘 Welcome Buttons
# ==========================================================

async def set_welcome_buttons(chat_id: int, buttons: list):
    await db.welcome.update_one(
        {"chat_id": chat_id},
        {"$set": {"buttons": buttons}},
        upsert=True
    )

async def get_welcome_buttons(chat_id: int):
    data = await db.welcome.find_one({"chat_id": chat_id})
    return data.get("buttons", []) if data else []

async def clear_welcome_buttons(chat_id: int):
    await db.welcome.update_one(
        {"chat_id": chat_id},
        {"$unset": {"buttons": ""}},
        upsert=True
    )


# ==========================================================
# 🔒 Lock
# ==========================================================

async def set_lock(chat_id, lock_type, status: bool):
    await db.locks.update_one(
        {"chat_id": chat_id},
        {"$set": {f"locks.{lock_type}": status}},
        upsert=True
    )

async def get_locks(chat_id):
    data = await db.locks.find_one({"chat_id": chat_id})
    return data.get("locks", {}) if data else {}


# ==========================================================
# ⚠️ Warn
# ==========================================================

async def add_warn(chat_id: int, user_id: int) -> int:
    data = await db.warns.find_one({"chat_id": chat_id, "user_id": user_id})
    warns = data.get("count", 0) + 1 if data else 1

    await db.warns.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"count": warns}},
        upsert=True
    )
    return warns

async def get_warns(chat_id: int, user_id: int) -> int:
    data = await db.warns.find_one({"chat_id": chat_id, "user_id": user_id})
    return data.get("count", 0) if data else 0

async def reset_warns(chat_id: int, user_id: int):
    await db.warns.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"count": 0}},
        upsert=True
    )


# ==========================================================
# 🧹 Cleanup
# ==========================================================

async def clear_group_data(chat_id: int):
    await db.welcome.delete_one({"chat_id": chat_id})
    await db.locks.delete_one({"chat_id": chat_id})
    await db.warns.delete_many({"chat_id": chat_id})
    await db.group_approvals.delete_one({"chat_id": chat_id})


# ==========================================================
# ✅ Group Approval System
# ==========================================================

async def set_group_approval(chat_id: int, status: str, approved_by: int = None):
    """
    status: 'pending' | 'approved' | 'rejected'
    """
    update = {"status": status}
    if approved_by:
        update["approved_by"] = approved_by
    await db.group_approvals.update_one(
        {"chat_id": chat_id},
        {"$set": update},
        upsert=True
    )

async def get_group_approval(chat_id: int) -> str:
    """Returns 'approved', 'rejected', 'pending', or None (not in DB)."""
    data = await db.group_approvals.find_one({"chat_id": chat_id})
    if data:
        return data.get("status", "pending")
    return None

async def is_group_approved(chat_id: int) -> bool:
    status = await get_group_approval(chat_id)
    return status == "approved"

async def get_all_pending_groups() -> list:
    groups = []
    async for doc in db.group_approvals.find({"status": "pending"}):
        groups.append(doc)
    return groups


# ==========================================================
# 👤 User
# ==========================================================

async def add_user(user_id, first_name):
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"first_name": first_name}},
        upsert=True
    )

async def get_all_users():
    users = []
    async for document in db.users.find({}, {"_id": 0, "user_id": 1}):
        if "user_id" in document:
            users.append(document["user_id"])
    return users