from aiogram import types

from ..config import dp
from ..queue import user_queue, user_queue_lock
from ..storage import save_data
from ..utils import fetch_russian_joke
from .number_request import update_queue_messages


@dp.message_handler(commands=["start"])
async def cmd_start(msg: types.Message) -> None:
    await msg.reply(
        "Привет! Отправь <b>номер</b>, чтобы получить номер телефона.\n"
        "Доступные команды: /help",
        parse_mode="HTML",
    )


@dp.message_handler(commands=["help"])
async def cmd_help(msg: types.Message) -> None:
    await msg.reply(
        "Доступные команды:\n"
        "/start — приветствие\n"
        "/help — список команд\n"
        "/queue — ваша позиция в очереди\n"
        "/leave — выйти из очереди\n"
        "/joke — случайный анекдот",
    )


@dp.message_handler(commands=["queue"])
async def cmd_queue(msg: types.Message) -> None:
    async with user_queue_lock:
        sorted_users = sorted(user_queue, key=lambda u: u["timestamp"])
        for idx, user in enumerate(sorted_users):
            if user["user_id"] == msg.from_user.id:
                await msg.reply(
                    f"⏳ Ваша позиция в очереди: <b>{idx + 1}</b>",
                    parse_mode="HTML",
                )
                break
        else:
            await msg.reply("⚠️ Вас нет в очереди.")


@dp.message_handler(commands=["leave"])
async def cmd_leave(msg: types.Message) -> None:
    removed = False
    async with user_queue_lock:
        for user in list(user_queue):
            if user["user_id"] == msg.from_user.id:
                user_queue.remove(user)
                removed = True
                break
    if removed:
        save_data()
        await update_queue_messages()
        await msg.reply("✅ Вы вышли из очереди.")
    else:
        await msg.reply("⚠️ Вас нет в очереди.")


@dp.message_handler(commands=["joke"])
async def cmd_joke(msg: types.Message) -> None:
    joke = fetch_russian_joke()
    await msg.reply(f"<code>{joke}</code>", parse_mode="HTML")
