from .commands import register_autodelete_system
from .scheduler import register_autodelete_scheduler


def register_autodelete_plugin(app):
    register_autodelete_system(app)
    register_autodelete_scheduler(app)
