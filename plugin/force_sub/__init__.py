# ============================================================
# plugin/force_sub/__init__.py
# ============================================================

from plugin.force_sub.force_sub import register_force_sub


def register_force_sub_plugin(app):
    register_force_sub(app)
    
