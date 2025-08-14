from aiogram import F, Router
from aiogram.enums import ChatType

# ``SkipHandler`` location changed between aiogram versions.  In aiogram 3 it
# lives in ``aiogram.exceptions`` but older releases exposed it from
# ``aiogram.dispatcher.handler``.  Attempt to import from the new location first
# and gracefully fall back to the old one so that the bot can start regardless
# of the installed aiogram version.
try:  # pragma: no cover - import resolution tested by running the bot
    from aiogram.exceptions import SkipHandler  # type: ignore
except Exception:  # pragma: no cover - executed on old aiogram versions
    from aiogram.dispatcher.handler import SkipHandler  # type: ignore

from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputFile, Message
from html import escape
import os

from ..config import logger
from ..queue import user_queue, user_queue_lock
from ..storage import save_data, issued_numbers
from ..utils import fetch_russian_joke
from .number_request import update_queue_messages

router = Router()


@router.message(F.chat.type == ChatType.PRIVATE)
async def ignore_private(msg: Message) -> None:
    """Ignore private messages."""
    logger.info(f"[PRIVATE MESSAGE IGNORED] user_id={msg.from_user.id}")
    raise SkipHandler()


@router.callback_query(F.message.chat.type == ChatType.PRIVATE)
async def ignore_private_callback(call: CallbackQuery) -> None:
    """Ignore callbacks from private chats."""
    logger.info(f"[PRIVATE CALLBACK IGNORED] user_id={call.from_user.id}")
    await call.answer()
    raise SkipHandler()


@router.message(Command(commands=["queue", "очередь"]))
async def cmd_queue(msg: Message) -> None:
    """Show user's position in queue."""
    logger.info(f"[CMD {msg.text}] user_id={msg.from_user.id}")
    async with user_queue_lock:
        for idx, user in enumerate(user_queue):
            if user["user_id"] == msg.from_user.id:
                await msg.reply(
                    f"⏳ Ваша позиция в очереди: <b>{idx + 1}</b>",
                )
                break
        else:
            await msg.reply("⚠️ Вас нет в очереди.")


@router.message(Command(commands=["leave"]))
async def cmd_leave(msg: Message) -> None:
    """Remove user from queue."""
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


@router.message(Command(commands=["joke", "анекдот"]))
async def cmd_joke(msg: Message) -> None:
    """Send random joke."""
    logger.info(f"[CMD {msg.text}] user_id={msg.from_user.id}")
    joke = fetch_russian_joke()
    await msg.reply(f"<code>{escape(joke)}</code>")


@router.message(Command(commands=["stats", "стат", "stat"]))
async def cmd_stats(msg: Message) -> None:
    """Show stats about issued numbers."""
    logger.info(f"[CMD {msg.text}] user_id={msg.from_user.id}")
    await msg.reply(
        f"\U0001F4CA Всего выдано номеров: <b>{len(issued_numbers)}</b>",
    )


@router.message(Command(commands=["выгруз"]))
async def cmd_dump(msg: Message) -> None:
    """Dump issued numbers to a file."""
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

