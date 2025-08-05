from bot.config import dp, logger
from aiogram import executor

if __name__ == "__main__":
    logger.info("Starting bot polling")
    executor.start_polling(dp, skip_updates=True)
