from os import getenv
import logging
import asyncio
from aiogram import Bot, Dispatcher, types

# Load environment variables from a .env file if python-dotenv is installed
try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass

API_TOKEN = getenv("API_TOKEN", "")
GROUP1_ID = int(getenv("GROUP1_ID", "0"))
GROUP2_IDS = [int(x) for x in getenv("GROUP2_IDS", "").split(",") if x]
TOPIC_IDS_GROUP1 = [int(x) for x in getenv("TOPIC_IDS_GROUP1", "").split(",") if x]
LOG_CHANNEL_ID = int(getenv("LOG_CHANNEL_ID", "0"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)


class TelegramLogsHandler(logging.Handler):
    """Send logs to a Telegram channel."""

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - network
        if not LOG_CHANNEL_ID:
            return
        log_entry = self.format(record)
        try:
            asyncio.create_task(bot.send_message(LOG_CHANNEL_ID, log_entry))
        except Exception:
            pass


if LOG_CHANNEL_ID:
    telegram_handler = TelegramLogsHandler()
    telegram_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(telegram_handler)
