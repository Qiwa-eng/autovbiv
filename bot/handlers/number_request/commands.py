import os
from datetime import datetime
from html import escape

from aiogram import types

from ..config import dp, bot, GROUP1_ID, GROUP2_IDS, TOPIC_IDS_GROUP1, logger
from ..queue import (
    number_queue,
    user_queue,
    bindings,
    IGNORED_TOPICS,
    number_queue_lock,
    user_queue_lock,
)
from ..storage import save_data, QUEUE_FILE
from ..utils import phone_pattern


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

