from os import getenv
import logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)
