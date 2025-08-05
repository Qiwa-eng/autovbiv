import os
import logging
from aiogram import Bot, Dispatcher, types

API_TOKEN = os.getenv('API_TOKEN', '')
GROUP1_ID = int(os.getenv('GROUP1_ID', '0'))
GROUP2_IDS = [int(x) for x in os.getenv('GROUP2_IDS', '').split(',') if x]
TOPIC_IDS_GROUP1 = [int(x) for x in os.getenv('TOPIC_IDS_GROUP1', '').split(',') if x]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)
