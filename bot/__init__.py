import asyncio

from .config import dp
from .storage import load_data, load_history
# Import general handlers before number_request so command handlers register first
from .handlers import general, number_request

load_data()
load_history()
asyncio.get_event_loop().create_task(number_request.joke_dispatcher())

__all__ = ["dp"]
