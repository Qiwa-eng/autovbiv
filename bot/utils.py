import re
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import random

phone_pattern = re.compile(r"(?:\+7|7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\b\d{10}\b")


def get_number_action_keyboard():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("\uD83D\uDD01 \u0421\u043A\u0438\u043F", callback_data="skip_number"),
        InlineKeyboardButton("\u274C \u041E\u0448\u0438\u0431\u043A\u0430", callback_data="error_reason")
    )

JOKES = [
    "— Мама, что такое черный юмор? — Сынок, видишь вон там мужчину без рук? Вели ему похлопать в ладоши. — Я же слепой! — Вот именно.",
    "Я копал яму в саду и вдруг откопал целый сундук с золотом. Потом вспомнил, зачем я копал яму.",
    "— Будешь выходить — труп вынеси! — Может мусор? — Может мусор, может сантехник, бог его знает…",
]


def fetch_russian_joke():
    return random.choice(JOKES)
