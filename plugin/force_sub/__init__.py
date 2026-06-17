# ============================================================
# plugin/force_sub/__init__.py
# ============================================================

from plugin.force_sub.force_sub import register_force_sub_plugin as _register

__all__ = ["register_force_sub_plugin"]


def register_force_sub_plugin(app):
    _register(app)

