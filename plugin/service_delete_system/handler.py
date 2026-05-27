# ============================================================
# plugin/service_delete_system/handler.py
#
# Single entry point imported by handlers/__init__.py.
# Registers both the admin commands and the service-message watcher.
# ============================================================

import logging
from pyrogram import Client

from .commands import register_service_delete_commands
from .watcher import register_service_delete_watcher

logger = logging.getLogger(__name__)


def register_service_delete_plugin(app: Client) -> None:
    """
    Wire up the entire service-delete feature:
      1. Admin commands  (/service_delete_on, /service_delete_off)
      2. Watcher         (new_chat_members, left_chat_member)
    """
    register_service_delete_commands(app)
    register_service_delete_watcher(app)
    logger.info("✅ ServiceDelete plugin fully loaded.")
    
