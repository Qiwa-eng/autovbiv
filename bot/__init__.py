import asyncio

from .config import bot, dp
from .storage import load_data, load_history
from .handlers.general import router as general_router
from .handlers.number_request import router as number_request_router, joke_dispatcher

load_data()
load_history()

dp.include_router(general_router)
dp.include_router(number_request_router)
asyncio.get_event_loop().create_task(joke_dispatcher())

__all__ = ["dp", "bot"]
