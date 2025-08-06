from aiogram import types
from aiogram.types import InputFile
from html import escape
import os

from aiogram.dispatcher.handler import CancelHandler
from ..config import dp, logger
from ..queue import user_queue, user_queue_lock
from ..storage import save_data, issued_numbers
from ..utils import fetch_russian_joke
from .number_request import update_queue_messages


@dp.message_handler(chat_type=types.ChatType.PRIVATE)
async def ignore_private(msg: types.Message) -> None:
    logger.info(f"[PRIVATE MESSAGE IGNORED] user_id={msg.from_user.id}")
    raise CancelHandler()


@dp.callback_query_handler(lambda c: c.message.chat.type == types.ChatType.PRIVATE)
async def ignore_private_callback(call: types.CallbackQuery) -> None:
    logger.info(f"[PRIVATE CALLBACK IGNORED] user_id={call.from_user.id}")
    await call.answer()
    raise CancelHandler()


@dp.message_handler(commands=["queue", "очередь"])
async def cmd_queue(msg: types.Message) -> None:
    logger.info(f"[CMD {msg.text}] user_id={msg.from_user.id}")
    async with user_queue_lock:
        for idx, user in enumerate(user_queue):
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
    logger.info(f"[CMD /leave] user_id={msg.from_user.id}")
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


@dp.message_handler(commands=["joke", "анекдот"])
async def cmd_joke(msg: types.Message) -> None:
    logger.info(f"[CMD {msg.text}] user_id={msg.from_user.id}")
    joke = fetch_russian_joke()
    await msg.reply(f"<code>{escape(joke)}</code>", parse_mode="HTML")


# Support multiple language variations for the stats command
@dp.message_handler(commands=["stats"])
@dp.message_handler(
    lambda m: m.text
    and m.text.lower().startswith( ("/стат", "/stat") )
)
async def cmd_stats(msg: types.Message) -> None:
    logger.info(f"[CMD {msg.text}] user_id={msg.from_user.id}")
    await msg.reply(
        f"\U0001F4CA Всего выдано номеров: <b>{len(issued_numbers)}</b>",
        parse_mode="HTML",
    )


@dp.message_handler(commands=["выгруз"])
async def cmd_dump(msg: types.Message) -> None:
    logger.info(f"[CMD /выгруз] user_id={msg.from_user.id}")
    if not issued_numbers:
        await msg.reply("⚠️ Номеров ещё не выдавалось.")
        return
    path = "issued_numbers.txt"
    with open(path, "w") as f:
        f.write("\n".join(issued_numbers))
    await msg.reply_document(InputFile(path), caption=f"Всего: {len(issued_numbers)}")
    try:
        os.remove(path)
    except Exception:
        pass
