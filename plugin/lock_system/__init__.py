from .commands import register_lock_system
from .lock_url import register_lock_url
from .lock_sticker import register_lock_sticker


def register_all_lock_plugins(app):
    register_lock_system(app)
    register_lock_url(app)
    register_lock_sticker(app)
    
