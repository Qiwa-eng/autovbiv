import asyncio

from bot import dp
from bot.config import bot, logger


async def main() -> None:
    """Start the bot with polling."""
    logger.info("Starting bot polling")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
