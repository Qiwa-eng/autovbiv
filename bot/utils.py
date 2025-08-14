import random
import re
from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

phone_pattern = re.compile(r"(?:\+7|7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\b\d{10}\b")


def get_number_action_keyboard():
    """Keyboard with actions for an issued number."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("1 код", callback_data="request_code1"),
        InlineKeyboardButton("2 код", callback_data="request_code2"),
    )
    kb.add(
        InlineKeyboardButton("\U0001F4F2 МТС звонки", callback_data="mts_calls"),
        InlineKeyboardButton("\U0001F4B0 Минусовой баланс", callback_data="neg_balance"),
    )
    return kb

JOKES: List[str] = [
    "— Мама, что такое черный юмор? — Сынок, видишь вон там мужчину без рук? Вели ему похлопать в ладоши. — Я же слепой! — Вот именно.",
    "Я копал яму в саду и вдруг откопал целый сундук с золотом. Потом вспомнил, зачем я копал яму.",
    "— Будешь выходить — труп вынеси! — Может мусор? — Может мусор, может сантехник, бог его знает…",
    "— Пап, а кто такой оптимист? — Это человек, который нашёл иголку в стоге сена и радуется, что не укололся.",
    "Звонок в дверь. Мужик открывает — перед ним курица с топором. \"Петух дома?\"",
    "— Доктор, все меня игнорируют! — Следующий!",
    "Встречаются два программиста: — Ты женат? — Нет. — И я тоже ноль.",
    "В ресторане: — Официант, у меня суп недосоленный. — Сейчас добавим поллитра!",
    "Говорят, что когда человек умирает, перед его глазами проходит вся жизнь. Поэтому у вас при смерти может зависнуть браузер.",
    "— Ты что, кушаешь в классе? — Это не я, это мой пищеварительный процесс.",
]

_available_jokes: List[str] = []


def fetch_russian_joke() -> str:
    """Return a random joke without immediate repetition."""
    global _available_jokes
    if not _available_jokes:
        _available_jokes = random.sample(JOKES, len(JOKES))
    return _available_jokes.pop()
