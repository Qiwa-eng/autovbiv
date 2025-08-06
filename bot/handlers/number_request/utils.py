import asyncio
from datetime import datetime
from html import escape

from aiogram import types
from aiogram.utils.exceptions import MessageNotModified, MessageToReplyNotFound

from ...config import dp, bot, GROUP1_ID, GROUP2_IDS, TOPIC_IDS_GROUP1, logger
from ...queue import (
    number_queue,
    user_queue,
    bindings,
    blocked_numbers,
    IGNORED_TOPICS,
    number_queue_lock,
    user_queue_lock,
    contact_bindings,
    active_numbers,
)
from ... import queue as queue_state
from ...storage import save_data, save_history, history, issued_numbers
from ...utils import get_number_action_keyboard, fetch_russian_joke


_queue_update_lock = asyncio.Lock()
_queue_last_update = 0.0


async def update_queue_messages():
    global _queue_last_update
    now = asyncio.get_event_loop().time()
    if now - _queue_last_update < 5:
        return
    async with _queue_update_lock:
        if now - _queue_last_update < 5:
            return
        _queue_last_update = now
        logger.debug("[ОЧЕРЕДЬ] обновление сообщений")
        async with user_queue_lock:
            users = list(user_queue)
        for idx, user in enumerate(users):
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

    msg_key = str(msg.reply_to_message.message_id)
    binding = bindings.get(msg_key)
    if not binding:
        return

    drop_id = binding.get("drop_id")
    number = binding.get("number") or binding.get("text")

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
        bindings.pop(msg_key, None)
        active_numbers.discard(number)
        contact_info = {
            "text": number,
            "group_id": binding["group_id"],
            "topic_id": binding["topic_id"],
            "orig_msg_id": binding["orig_msg_id"],
        }
        if drop_id:
            contact_info["drop_id"] = drop_id
        contact_bindings[msg_key] = contact_info
        save_data()


async def joke_dispatcher():
    sent_users = set()
    while True:
        now = datetime.utcnow().timestamp()
        for user in list(user_queue):
            ts = user["timestamp"]
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
    if not queue_state.WORKING:
        return
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

    while queue_state.WORKING:
        async with number_queue_lock:
            async with user_queue_lock:
                if number_queue and user_queue:
                    number = number_queue.popleft()
                    user = user_queue.popleft()
                else:
                    break

        if not queue_state.WORKING:
            async with number_queue_lock:
                number_queue.appendleft(number)
            async with user_queue_lock:
                user_queue.appendleft(user)
            break

        asyncio.create_task(update_queue_messages())

        message_text = (
            f"🎉 <b>Ваш номер:</b> <code>{escape(number['text'])}</code>\n\n"
            "✉️ <i>Ответьте на это сообщение и отправьте код.</i>\n"
            "⚠️ <b>Если есть проблема</b>, воспользуйтесь кнопкой ниже и приложите <u>скрин</u>."
        )
        send_kwargs = {
            "chat_id": user["chat_id"],
            "text": message_text,
            "reply_to_message_id": user["request_msg_id"],
            "reply_markup": get_number_action_keyboard(),
            "parse_mode": "HTML",
        }
        try:
            sent = await bot.send_message(**send_kwargs)
        except MessageToReplyNotFound:
            logger.warning(
                f"[ОШИБКА ОТПРАВКИ] user_id={user['user_id']}: Message to be replied not found"
            )
            send_kwargs.pop("reply_to_message_id", None)
            try:
                sent = await bot.send_message(**send_kwargs)
            except Exception as e:
                logger.warning(f"[ОШИБКА ОТПРАВКИ] user_id={user['user_id']}: {e}")
                async with number_queue_lock:
                    number_queue.appendleft(number)
                async with user_queue_lock:
                    user_queue.appendleft(user)
                save_data()
                asyncio.create_task(update_queue_messages())
                continue
        except Exception as e:
            logger.warning(f"[ОШИБКА ОТПРАВКИ] user_id={user['user_id']}: {e}")
            async with number_queue_lock:
                number_queue.appendleft(number)
            async with user_queue_lock:
                user_queue.appendleft(user)
            save_data()
            asyncio.create_task(update_queue_messages())
            continue

        bindings[str(sent.message_id)] = {
            "orig_msg_id": number['message_id'],
            "topic_id": number['topic_id'],
            "group_id": number['from_group_id'],
            "user_id": user['user_id'],
            "text": number['text'],
            "number": number.get('number'),
            "added_at": number.get("added_at"),
            "queue_data": user.copy(),
        }
        issued_numbers.append(number["text"])
        save_data()
        logger.info(
            f"[АВТОВЫДАЧА] {number['text']} → user_id={user['user_id']}"
        )
