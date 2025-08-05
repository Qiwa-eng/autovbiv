import asyncio

from .config import dp
from .storage import load_data, load_history
from .handlers import number_request, general

load_data()
load_history()
asyncio.get_event_loop().create_task(number_request.joke_dispatcher())

__all__ = ["dp"]
