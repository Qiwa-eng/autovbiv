import os
from datetime import datetime
from statistics import mean
from html import escape

from aiogram import types

from ...config import dp, bot, GROUP1_ID, GROUP2_IDS, TOPIC_IDS_GROUP1, logger
from ...queue import (
    number_queue,
    user_queue,
    bindings,
    blocked_numbers,
    IGNORED_TOPICS,
    number_queue_lock,
    user_queue_lock,
)
from ... import queue as queue_state
from ...storage import save_data, history, issued_numbers
from ...utils import phone_pattern, get_number_action_keyboard
from .utils import update_queue_messages, try_dispatch_next


@dp.message_handler(lambda msg: msg.text and msg.text.lower() == "номер")
async def handle_number_request(msg: types.Message):
    logger.info(
        f"[ЗАПРОС НОМЕРА] user_id={msg.from_user.id} chat_id={msg.chat.id} topic={msg.message_thread_id}"
    )
    if not queue_state.WORKING:
        return await msg.reply("⏸️ Бот сейчас не выдаёт номера.")
    if msg.chat.type == "private":
        logger.debug(f"[ЗАПРОС НОМЕРА] user_id={msg.from_user.id} в приватном чате")
        return await msg.reply(
            "❌ Команда <b>номер</b> работает только в группе.", parse_mode="HTML"
        )

    if msg.message_thread_id in IGNORED_TOPICS:
        logger.debug(
            f"[ЗАПРОС НОМЕРА] тема {msg.message_thread_id} в списке игнора"
        )
        return await msg.reply(
            "⚠️ В этой теме бот не работает. Активируйте её командой /work."
        )

    if msg.chat.id not in GROUP2_IDS:
        logger.debug(f"[ЗАПРОС НОМЕРА] чат {msg.chat.id} не разрешён")
        return

    async with user_queue_lock:
        for entry in user_queue:
            if entry['user_id'] == msg.from_user.id:
                logger.debug(
                    f"[ЗАПРОС НОМЕРА] user_id={msg.from_user.id} уже в очереди"
                )
                return await msg.reply("⚠️ Вы уже в очереди на номер.")

    async with number_queue_lock:
        if number_queue:
            number = number_queue.popleft()
        else:
            number = None

    if number:
        message_text = (
            f"🎉 <b>Ваш номер:</b> <code>{escape(number['text'])}</code>\n\n"
            "✉️ <i>Ответьте на это сообщение и отправьте код.</i>\n"
            "⚠️ <b>Если есть проблема</b>, воспользуйтесь кнопкой ниже и приложите <u>скрин</u>."
        )

        sent = await bot.send_message(
            chat_id=msg.chat.id,
            text=message_text,
            reply_to_message_id=msg.message_id,
            reply_markup=get_number_action_keyboard(),
            parse_mode="HTML",
        )

        bindings[str(sent.message_id)] = {
            "orig_msg_id": number['message_id'],
            "topic_id": number['topic_id'],
            "group_id": number['from_group_id'],
            "user_id": msg.from_user.id,
            "drop_id": number.get("drop_id"),
            "text": number['text'],
            "added_at": number.get("added_at"),
        }
        issued_numbers.append(number["text"])
        save_data()
        logger.info(f"[ВЫДАН НОМЕР] {number['text']} → user_id={msg.from_user.id}")
    else:
        async with user_queue_lock:
            position = len(user_queue) + 1
        logger.info(f"[ОЧЕРЕДЬ] user_id={msg.from_user.id} позиция {position}")
        notify = await msg.reply(
            f"⏳ <b>Свободных номеров нет.</b>\nВаша позиция в очереди: <b>{position}</b>",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("🚪 Выйти из очереди", callback_data="leave_queue")
            ),
        )

        async with user_queue_lock:
            user_queue.append(
                {
                    "user_id": msg.from_user.id,
                    "chat_id": msg.chat.id,
                    "request_msg_id": msg.message_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "notify_msg_id": notify.message_id,
                }
            )
            queue_len = len(user_queue)
            logger.debug(f"[ОЧЕРЕДЬ] размер: {queue_len}")
            if queue_len > 10:
                logger.critical(f"[ОЧЕРЕДЬ] слишком много ожидающих: {queue_len}")

        save_data()
        await try_dispatch_next()
        await update_queue_messages()


@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_number_sources(msg: types.Message):
    if not queue_state.WORKING:
        return
    if msg.message_thread_id in IGNORED_TOPICS:
        return
    if msg.chat.type == "private":
        return

    if msg.chat.id == GROUP1_ID and msg.message_thread_id in TOPIC_IDS_GROUP1:
        match = phone_pattern.search(msg.text)
        if not match:
            return

        number_text = match.group(0)

        blocked_until = blocked_numbers.get(number_text)
        now_ts = datetime.utcnow().timestamp()
        if blocked_until:
            if blocked_until > now_ts:
                await bot.send_message(
                    chat_id=msg.chat.id,
                    message_thread_id=msg.message_thread_id,
                    reply_to_message_id=msg.message_id,
                    text="⛔ Этот номер временно заблокирован",
                )
                logger.info(f"[ЗАБЛОКИРОВАННЫЙ НОМЕР] {number_text}")
                return
            else:
                blocked_numbers.pop(number_text, None)

        async with number_queue_lock:
            duplicate_in_queue = any(
                number_text in item.get("text", "") for item in number_queue
            )
            duplicate_in_bindings = any(
                number_text in item.get("text", "") for item in bindings.values()
            )
            duplicate = duplicate_in_queue or duplicate_in_bindings
            if not duplicate:
                number_queue.append(
                    {
                        "message_id": msg.message_id,
                        "topic_id": msg.message_thread_id,
                        "text": msg.text,
                        "from_group_id": msg.chat.id,
                        "drop_id": msg.from_user.id,
                        "added_at": datetime.utcnow().timestamp(),
                    }
                )
        if duplicate:
            await bot.send_message(
                chat_id=msg.chat.id,
                message_thread_id=msg.message_thread_id,
                reply_to_message_id=msg.message_id,
                text="⚠️ Такой номер уже в очереди или выдан",
            )
            logger.info(f"[ДУБЛИКАТ] {number_text}")
            return

        save_data()

        if history:
            avg_delay = int(
                mean(entry["delay"] for entry in history if "delay" in entry)
            )
            avg_delay = max(5, min(avg_delay, 1800))
            minutes = avg_delay // 60
            seconds = avg_delay % 60
            estimate = f"{minutes} мин {seconds} сек"
        else:
            estimate = "недоступно"

        await bot.send_message(
            chat_id=msg.chat.id,
            message_thread_id=msg.message_thread_id,
            reply_to_message_id=msg.message_id,
            text=f"✅ Взял номер\n\n⏱ Примерное ожидание кода: <b>{escape(estimate)}</b>",
            parse_mode="HTML",
        )

        logger.info(
            f"[НОМЕР ПРИНЯТ] {number_text} из темы {msg.message_thread_id}"
        )
        await try_dispatch_next()

