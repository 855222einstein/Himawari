# ============================================================
# handlers/__init__.py
# ============================================================

from handlers.start import register_handlers
from handlers.group_commands import register_group_commands
from handlers.owner import register_owner_handlers

from plugin.lock_system import register_all_lock_plugins
from plugin.group_guard import register_group_guard
from plugin.autodelete_system import register_autodelete_plugin
from plugin.service_delete_system import register_service_delete_plugin
from plugin.force_sub.force_sub import register_force_sub_plugin


def register_all_handlers(app):
    register_handlers(app)
    register_group_commands(app)
    register_owner_handlers(app)
    register_all_lock_plugins(app)
    register_group_guard(app)
    register_autodelete_plugin(app)
    register_service_delete_plugin(app)
    register_force_sub_plugin(app)
    print("✅ All handlers loaded successfully")
    
