from os import getenv
import os
import json
import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

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
ADMIN_ID = int(getenv("ADMIN_ID", "0"))

IDS_FILE = "ids.json"


def load_ids() -> None:
    global GROUP1_ID, GROUP2_IDS, TOPIC_IDS_GROUP1
    if os.path.exists(IDS_FILE):
        try:
            with open(IDS_FILE, "r") as f:
                data = json.load(f)
            GROUP1_ID = data.get("GROUP1_ID", GROUP1_ID)
            GROUP2_IDS = data.get("GROUP2_IDS", GROUP2_IDS)
            TOPIC_IDS_GROUP1 = data.get("TOPIC_IDS_GROUP1", TOPIC_IDS_GROUP1)
        except Exception:
            pass
    else:
        save_ids()


def save_ids() -> None:
    data = {
        "GROUP1_ID": GROUP1_ID,
        "GROUP2_IDS": GROUP2_IDS,
        "TOPIC_IDS_GROUP1": TOPIC_IDS_GROUP1,
    }
    try:
        with open(IDS_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


load_ids()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# aiogram 3.7 removed ``parse_mode`` from ``Bot`` initializer. Configure
# default settings via ``DefaultBotProperties`` instead.
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


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
