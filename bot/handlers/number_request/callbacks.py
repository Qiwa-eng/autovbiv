from datetime import datetime, timedelta

from aiogram import types

from ...config import dp, bot, GROUP2_IDS, logger
from ...queue import (
    number_queue,
    user_queue,
    bindings,
    contact_bindings,
    blocked_numbers,
    contact_requests,
    number_queue_lock,
    user_queue_lock,
)
from ...storage import save_data
from .utils import update_queue_messages, try_dispatch_next


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


@dp.callback_query_handler(lambda c: c.data == "contact_drop")
async def handle_contact_drop(call: types.CallbackQuery):
    msg_id = call.message.message_id
    msg_key = str(msg_id)
    binding = bindings.get(msg_key) or contact_bindings.get(msg_key)

    if not binding:
        return await call.answer("⚠️ Номер не найден или уже обработан.", show_alert=True)

    drop_id = binding.get("drop_id")
    if not drop_id:
        return await call.answer("⚠️ Невозможно связаться с дропом.", show_alert=True)

    contact_requests[call.from_user.id] = {
        "drop_id": drop_id,
        "number": binding.get("text"),
    }
    await call.message.reply("Введите ваше сообщение либо фото:")
    await call.answer()


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


@dp.message_handler(lambda msg: msg.from_user.id in contact_requests, content_types=types.ContentTypes.ANY)
async def forward_contact_message(msg: types.Message):
    info = contact_requests.pop(msg.from_user.id)
    drop_id = info["drop_id"]
    number = info.get("number")

    try:
        if msg.photo:
            caption = f"По номеру {number} от пользователя {msg.from_user.id}\n{msg.caption or ''}"
            await bot.send_photo(drop_id, msg.photo[-1].file_id, caption=caption)
        elif msg.text:
            text = f"Сообщение по номеру {number} от пользователя {msg.from_user.id}:\n{msg.text}"
            await bot.send_message(drop_id, text)
        else:
            await msg.reply("⚠️ Поддерживаются только текст и фото.")
            return
        await msg.reply("✅ Сообщение отправлено дропу.")
    except Exception as e:
        logger.warning(f"[ОШИБКА ОТПРАВКИ ДРОПУ] {e}")
        await msg.reply("⚠️ Не удалось отправить сообщение дропу.")


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
