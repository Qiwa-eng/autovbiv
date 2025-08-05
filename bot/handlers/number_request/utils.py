import asyncio
from datetime import datetime
from html import escape

from aiogram import types
from aiogram.utils.exceptions import MessageNotModified

from ..config import dp, bot, GROUP1_ID, GROUP2_IDS, TOPIC_IDS_GROUP1, logger
from ..queue import (
    number_queue,
    user_queue,
    bindings,
    blocked_numbers,
    IGNORED_TOPICS,
    number_queue_lock,
    user_queue_lock,
)
from ..storage import save_data, save_history, history, issued_numbers
from ..utils import get_number_action_keyboard, fetch_russian_joke


async def update_queue_messages():
    logger.debug("[ОЧЕРЕДЬ] обновление сообщений")
    for idx, user in enumerate(sorted(user_queue, key=lambda x: x["timestamp"])):
        try:
            position = idx + 1
            await bot.edit_message_text(
                chat_id=user["chat_id"],
                message_id=user["notify_msg_id"],
                text=(
                    "⏳ <b>Ожидание номера</b>\n"
                    f"Ваша позиция: <b>{position}</b>"
                ),
                parse_mode="HTML",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton(
                        "🚪 Выйти из очереди", callback_data="leave_queue"
                    )
                ),
            )
        except MessageNotModified:
            logger.debug(
                f"[ОЧЕРЕДЬ] сообщение {user['notify_msg_id']} без изменений"
            )
            continue
        except Exception as e:
            logger.warning(
                f"[ОШИБКА ОБНОВЛЕНИЯ ОЧЕРЕДИ] user_id={user['user_id']}: {e}"
            )


@dp.message_handler(content_types=types.ContentTypes.PHOTO)
async def handle_photo_response(msg: types.Message):
    if not msg.reply_to_message:
        return

    binding = bindings.get(str(msg.reply_to_message.message_id))
    if not binding:
        return

    try:
        await bot.send_photo(
            chat_id=binding['group_id'],
            photo=msg.photo[-1].file_id,
            message_thread_id=binding['topic_id'],
            reply_to_message_id=binding['orig_msg_id'],
        )

        await msg.reply("✅ Код был успешно отправлен")

        added_at = binding.get("added_at")
        if added_at:
            now = datetime.utcnow().timestamp()
            delay = now - added_at
            history.append({"added": added_at, "responded": now, "delay": delay})
            history[:] = history[-50:]
            save_history()
            logger.info(
                f"[КОД ПОЛУЧЕН] user_id={binding['user_id']} — ожидание {int(delay)} сек"
            )

    except Exception as e:
        logger.warning(f"[ОШИБКА ОТПРАВКИ КОДА] {e}")
        await msg.reply(
            "❌ Не удалось отправить код.\n"
            "Пожалуйста, запросите новый номер — он не найден в чате с номерами.",
        )
    finally:
        bindings.pop(str(msg.reply_to_message.message_id), None)
        save_data()


async def joke_dispatcher():
    sent_users = set()
    while True:
        now = datetime.utcnow().timestamp()
        for user in list(user_queue):
            ts = datetime.fromisoformat(user["timestamp"]).timestamp()
            if now - ts >= 60 and user['user_id'] not in sent_users:
                joke = fetch_russian_joke()
                try:
                    await bot.send_message(
                        chat_id=user["chat_id"],
                        text=f"🕓 Пока вы ждёте, вот вам анекдот:\n\n<code>{escape(joke)}</code>",
                        parse_mode="HTML",
                        reply_to_message_id=user.get("request_msg_id"),
                    )
                    sent_users.add(user['user_id'])
                except Exception as e:
                    logger.warning(f"[АНЕКДОТ] user_id={user['user_id']}: {e}")
        await asyncio.sleep(30)


async def try_dispatch_next():
    async with number_queue_lock:
        empty_numbers = not number_queue
    async with user_queue_lock:
        has_users = bool(user_queue)

    if empty_numbers and has_users:
        now = datetime.utcnow().timestamp()
        if not hasattr(try_dispatch_next, "last_notice") or now - try_dispatch_next.last_notice > 120:
            try_dispatch_next.last_notice = now
            for topic_id in TOPIC_IDS_GROUP1:
                try:
                    await bot.send_message(
                        chat_id=GROUP1_ID,
                        message_thread_id=topic_id,
                        text="🚨 Очередь номеров пуста! Самые быстрые коды на диком западе!",
                    )
                    logger.info(f"[ОПОВЕЩЕНИЕ] Пустая очередь → тема {topic_id}")
                except Exception as e:
                    logger.warning(f"[ОШИБКА ОПОВЕЩЕНИЯ] тема {topic_id}: {e}")
        return

    while True:
        async with number_queue_lock:
            async with user_queue_lock:
                if number_queue and user_queue:
                    number = number_queue.popleft()
                    sorted_users = sorted(
                        user_queue,
                        key=lambda u: datetime.fromisoformat(u['timestamp'])
                    )
                    user = sorted_users[0]
                    user_queue.remove(user)
                else:
                    break

        await update_queue_messages()

        message_text = (
            f"🎉 <b>Ваш номер:</b> <code>{escape(number['text'])}</code>\n\n"
            "✉️ <i>Ответьте на это сообщение и отправьте код.</i>\n"
            "⚠️ <b>Если есть проблема</b>, воспользуйтесь кнопкой ниже и приложите <u>скрин</u>."
        )
        try:
            sent = await bot.send_message(
                chat_id=user['chat_id'],
                text=message_text,
                reply_to_message_id=user['request_msg_id'],
                reply_markup=get_number_action_keyboard(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"[ОШИБКА ОТПРАВКИ] user_id={user['user_id']}: {e}")
            async with user_queue_lock:
                user_queue.appendleft(user)
            await update_queue_messages()
            continue

        bindings[str(sent.message_id)] = {
            "orig_msg_id": number['message_id'],
            "topic_id": number['topic_id'],
            "group_id": number['from_group_id'],
            "user_id": user['user_id'],
            "text": number['text'],
            "added_at": number.get("added_at"),
            "queue_data": user.copy(),
        }
        issued_numbers.append(number["text"])
        save_data()
        logger.info(
            f"[АВТОВЫДАЧА] {number['text']} → user_id={user['user_id']}"
        )
