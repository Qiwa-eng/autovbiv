import asyncio
import os
from datetime import datetime, timedelta
from statistics import mean
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
from ..storage import (
    save_data,
    load_data,
    load_history,
    save_history,
    history,
    issued_numbers,
    QUEUE_FILE,
)
from ..utils import phone_pattern, get_number_action_keyboard, fetch_russian_joke


@dp.message_handler(lambda msg: msg.text and msg.text.lower() == "номер")
async def handle_number_request(msg: types.Message):
    logger.info(
        f"[ЗАПРОС НОМЕРА] user_id={msg.from_user.id} chat_id={msg.chat.id} topic={msg.message_thread_id}"
    )
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


@dp.callback_query_handler(lambda c: c.data == "error_reason")
async def error_reason_menu(call: types.CallbackQuery):
    keyboard = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("💥 Моментальная ошибка", callback_data="error_ban"),
        types.InlineKeyboardButton("⌛ Код не пришёл", callback_data="error_noban"),
    )
    await call.message.edit_text(
        f"{call.message.html_text}\n\n<b>Выберите причину:</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


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


@dp.message_handler(commands=["work"])
async def remove_topic_from_ignore(msg: types.Message):
    if msg.message_thread_id is not None:
        if msg.message_thread_id in IGNORED_TOPICS:
            IGNORED_TOPICS.remove(msg.message_thread_id)
            await msg.reply(
                "✅ Эта тема снова активна. Бот теперь реагирует на номера."
            )
            save_data()
        else:
            await msg.reply("ℹ️ Эта тема и так уже активна.")
    else:
        await msg.reply("⚠️ Команду можно использовать только в теме.")


@dp.message_handler(commands=["удалить", "delete"])
async def remove_number_from_queue(msg: types.Message):
    if msg.chat.id not in {GROUP1_ID, *GROUP2_IDS}:
        return

    target_id = None
    number_text = None

    if msg.reply_to_message:
        target_id = msg.reply_to_message.message_id
        match = phone_pattern.search(msg.reply_to_message.text or "")
        if match:
            number_text = match.group(0)

    if not number_text:
        match = phone_pattern.search(msg.get_args())
        if match:
            number_text = match.group(0)

    removed = False
    async with number_queue_lock:
        for item in list(number_queue):
            if (
                (target_id and item.get("message_id") == target_id)
                or (number_text and number_text in item.get("text", ""))
            ):
                number_queue.remove(item)
                removed = True
                if not number_text:
                    match = phone_pattern.search(item.get("text", ""))
                    if match:
                        number_text = match.group(0)
                break

    if removed:
        save_data()
        await msg.reply(
            f"✅ Номер <code>{escape(number_text)}</code> удалён из очереди.",
            parse_mode="HTML",
        )
        logger.info(f"[УДАЛЕНИЕ] {number_text} → user_id={msg.from_user.id}")
    else:
        await msg.reply("⚠️ Номер не найден в очереди.")


@dp.message_handler(commands=["очистить"])
async def handle_clear_queue(msg: types.Message):
    if msg.chat.id not in GROUP2_IDS:
        return

    async with number_queue_lock:
        number_queue.clear()
    async with user_queue_lock:
        user_queue.clear()
    bindings.clear()
    save_data()

    for topic_id in TOPIC_IDS_GROUP1:
        try:
            await bot.send_message(
                chat_id=GROUP1_ID,
                message_thread_id=topic_id,
                text="⚠️ Очередь очищена, продублируйте номера",
            )
            logger.info(f"[ОЧИСТКА] Сообщение отправлено в тему {topic_id}")
        except Exception as e:
            logger.warning(f"[ОШИБКА ПРИ ОЧИСТКЕ] Тема {topic_id}: {e}")

    await msg.reply("Очередь очищена ✅")
    logger.info(f"[ОЧИСТКА] Инициирована пользователем {msg.from_user.id}")


@dp.message_handler(commands=["очередь"])
async def handle_queue_status(msg: types.Message):
    if msg.chat.id not in GROUP2_IDS:
        return

    num_numbers = len(number_queue)
    num_users = len(user_queue)

    if num_users == 0:
        est_wait = "Мгновенно"
    elif num_numbers == 0:
        est_wait = "ожидание номера"
    else:
        seconds_total = num_users * 30
        minutes = seconds_total // 60
        seconds = seconds_total % 60
        est_wait = f"~{minutes} мин {seconds} сек"

    if os.path.exists(QUEUE_FILE):
        timestamp = os.path.getmtime(QUEUE_FILE)
        last_updated = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
    else:
        last_updated = "н/д"

    text = (
        "📊 <b>Текущая очередь</b>\n\n"
        f"🔢 <b>Номеров доступно:</b> <code>{num_numbers}</code>\n"
        f"👥 <b>Ожидающих пользователей:</b> <code>{num_users}</code>\n\n"
        f"⏱️ <b>Ожидание:</b> <i>{est_wait}</i>\n"
        f"🕒 <b>Обновлено:</b> <i>{last_updated}</i>\n\n"
        "💡 <i>Чем быстрее коды — тем быстрее номера 🐎</i>"
    )

    await msg.reply(text)


@dp.callback_query_handler(lambda c: c.data == "skip_number")
async def handle_skip_number(call: types.CallbackQuery):
    msg_id = call.message.message_id
    user_id = call.from_user.id
    binding = bindings.get(str(msg_id))

    if not binding:
        return await call.answer("⚠️ Номер не найден или уже обработан.", show_alert=True)

    number_text = binding["text"]

    async with number_queue_lock:
        number_queue.append(
            {
                "message_id": binding["orig_msg_id"],
                "topic_id": binding["topic_id"],
                "text": number_text,
                "from_group_id": binding["group_id"],
                "added_at": binding.get("added_at", datetime.utcnow().timestamp()),
            }
        )

    try:
        await call.message.edit_text("🔄 Номер возвращён в очередь.")
    except Exception:
        await call.message.reply("🔄 Номер возвращён в очередь.")

    logger.info(f"[СКИП] {number_text} → user_id={user_id}")

    bindings.pop(str(msg_id), None)
    save_data()
    await try_dispatch_next()


@dp.callback_query_handler(lambda c: c.data in ["error_ban", "error_noban"])
async def handle_error_choice(call: types.CallbackQuery):
    msg_id = call.message.message_id
    user_id = call.from_user.id
    binding = bindings.get(str(msg_id))

    if not binding:
        return await call.answer("Номер уже обработан.", show_alert=True)

    number_text = binding["text"]

    if call.data == "error_ban":
        blocked_until = datetime.utcnow() + timedelta(minutes=30)
        blocked_numbers[number_text] = blocked_until.timestamp()
        await call.message.edit_text(
            "🚫 Номер удалён.\n⛔ Заблокирован на 30 минут (моментальная ошибка)."
        )
        reason = "моментальная ошибка"
        logger.info(f"[ОШИБКА С БАНОМ] {number_text} → user_id={user_id}")
    else:
        await call.message.edit_text(
            "🚫 Номер удалён.\n⌛ Код не пришёл."
        )
        reason = "не пришёл код"
        logger.info(f"[ОШИБКА БЕЗ БАНА] {number_text} → user_id={user_id}")

    try:
        await bot.send_message(
            chat_id=binding["group_id"],
            message_thread_id=binding["topic_id"],
            reply_to_message_id=binding["orig_msg_id"],
            text=f"⚠️ Пользователь сообщил об ошибке: {reason}",
        )
    except Exception as e:
        logger.warning(f"[ОШИБКА ОПОВЕЩЕНИЯ ОШИБКИ] {e}")

    queue_user = binding.get("queue_data")
    if queue_user:
        async with user_queue_lock:
            user_queue.append(queue_user)
        await update_queue_messages()

    bindings.pop(str(msg_id), None)
    save_data()
    await try_dispatch_next()


@dp.message_handler(commands=["id"])
async def handle_id_command(msg: types.Message):
    chat_id = msg.chat.id
    thread_id = msg.message_thread_id

    text = f"<b>Chat ID:</b> <code>{chat_id}</code>"
    if thread_id is not None:
        text += f"\n<b>Topic (Thread) ID:</b> <code>{thread_id}</code>"

    await msg.reply(text)


@dp.message_handler(commands=["nework"])
async def add_topic_to_ignore(msg: types.Message):
    if msg.message_thread_id is not None:
        IGNORED_TOPICS.add(msg.message_thread_id)
        save_data()
        await msg.reply(
            "✅ Эта тема теперь исключена. Бот не будет здес реагировать на номера."
        )
    else:
        await msg.reply("⚠️ Команду можно использовать только внутри темы.")


@dp.message_handler(content_types=types.ContentTypes.TEXT)
async def handle_number_sources(msg: types.Message):
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


@dp.callback_query_handler(lambda c: c.data == "leave_queue")
async def leave_queue(call: types.CallbackQuery):
    if call.message.chat.id not in GROUP2_IDS:
        return

    async with user_queue_lock:
        removed = False
        new_queue = []
        for u in user_queue:
            if u['user_id'] == call.from_user.id:
                removed = True
            else:
                new_queue.append(u)

        if removed:
            user_queue.clear()
            user_queue.extend(new_queue)

    if removed:
        try:
            await call.message.edit_text("🚪 Вы покинули очередь.")
        except Exception:
            await call.message.reply("🚪 Вы покинули очередь.")
        logger.info(f"[ВЫХОД ИЗ ОЧЕРЕДИ] user_id={call.from_user.id}")
    else:
        await call.answer("Вы не были в очереди.", show_alert=True)

    save_data()
    await update_queue_messages()


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
