from aiogram import Router

router = Router()

# Register submodules to attach handlers to the router
from . import callbacks, commands, request  # noqa: F401
from .utils import update_queue_messages, handle_photo_response, joke_dispatcher, try_dispatch_next

__all__ = [
    "router",
    "update_queue_messages",
    "handle_photo_response",
    "joke_dispatcher",
    "try_dispatch_next",
]
