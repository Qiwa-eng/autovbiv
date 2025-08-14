from datetime import datetime, timedelta

from aiogram import F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from ...config import bot, GROUP2_IDS, logger
from ...queue import (
    number_queue,
    user_queue,
    bindings,
    contact_bindings,
    blocked_numbers,
    contact_requests,
    number_queue_lock,
    user_queue_lock,
    active_numbers,
    pending_code_requests,
    pending_balance_requests,
)
from ...storage import save_data
from .utils import update_queue_messages, try_dispatch_next
from . import router


@router.callback_query(F.data == "error_reason")
async def error_reason_menu(call: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("💥 Моментальная ошибка", callback_data="error_ban"),
         InlineKeyboardButton("⌛ Код не пришёл", callback_data="error_noban")]
    ])
    await call.message.edit_text(
        f"{call.message.html_text}\n\n<b>Выберите причину:</b>",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "skip_number")
async def handle_skip_number(call: CallbackQuery) -> None:
    msg_id = call.message.message_id
    user_id = call.from_user.id
    binding = bindings.get(str(msg_id))

    if not binding:
        return await call.answer("⚠️ Номер не найден или уже обработан.", show_alert=True)

    number_text = binding.get("number") or binding["text"]

    async with number_queue_lock:
        number_queue.append(
            {
                "message_id": binding["orig_msg_id"],
                "topic_id": binding["topic_id"],
                "text": number_text,
                "number": number_text,
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


@router.callback_query(F.data == "contact_drop")
async def handle_contact_drop(call: CallbackQuery) -> None:
    msg_id = call.message.message_id
    msg_key = str(msg_id)
    binding = bindings.get(msg_key) or contact_bindings.get(msg_key)

    if not binding:
        return await call.answer("⚠️ Номер не найден или уже обработан.", show_alert=True)

    contact_requests[call.from_user.id] = {
        "number": binding.get("number") or binding.get("text"),
        "group_id": binding.get("group_id"),
        "topic_id": binding.get("topic_id"),
        "orig_msg_id": binding.get("orig_msg_id"),
    }
    drop_id = binding.get("drop_id")
    if drop_id:
        contact_requests[call.from_user.id]["drop_id"] = drop_id
    await call.message.reply("Введите ваше сообщение либо фото:")
    await call.answer()


@router.callback_query(F.data.in_({"error_ban", "error_noban"}))
async def handle_error_choice(call: CallbackQuery) -> None:
    msg_id = call.message.message_id
    user_id = call.from_user.id
    binding = bindings.get(str(msg_id))

    if not binding:
        return await call.answer("Номер уже обработан.", show_alert=True)

    number_text = binding.get("number") or binding["text"]

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
    active_numbers.discard(number_text)
    save_data()
    await try_dispatch_next()


@router.message(lambda msg: msg.from_user.id in contact_requests)
async def forward_contact_message(msg: Message) -> None:
    info = contact_requests.pop(msg.from_user.id)
    number = info.get("number")
    group_id = info.get("group_id")
    topic_id = info.get("topic_id")
    orig_msg_id = info.get("orig_msg_id")

    try:
        if msg.photo:
            caption = f"По номеру {number} от пользователя {msg.from_user.id}\n{msg.caption or ''}"
            await bot.send_photo(
                chat_id=group_id,
                photo=msg.photo[-1].file_id,
                caption=caption,
                message_thread_id=topic_id,
                reply_to_message_id=orig_msg_id,
            )
        elif msg.text:
            text = f"Сообщение по номеру {number} от пользователя {msg.from_user.id}:\n{msg.text}"
            await bot.send_message(
                chat_id=group_id,
                text=text,
                message_thread_id=topic_id,
                reply_to_message_id=orig_msg_id,
            )
        else:
            await msg.reply("⚠️ Поддерживаются только текст и фото.")
            return
        await msg.reply("✅ Сообщение отправлено в группу.")
    except Exception as e:
        logger.warning(f"[ОШИБКА ОТПРАВКИ В ГРУППУ] {e}")
        await msg.reply("⚠️ Не удалось отправить сообщение в группу.")


@router.callback_query(F.data == "leave_queue")
async def leave_queue(call: CallbackQuery) -> None:
    if call.message.chat.id not in GROUP2_IDS:
        return

    async with user_queue_lock:
        removed = False
        new_queue = []
        for u in user_queue:
            if u["user_id"] == call.from_user.id:
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
        await call.answer("⚠️ Вас нет в очереди.", show_alert=True)


@router.callback_query(F.data.in_({"request_code1", "request_code2"}))
async def handle_code_request(call: CallbackQuery) -> None:
    msg_id = call.message.message_id
    binding = bindings.get(str(msg_id))
    if not binding:
        return await call.answer("⚠️ Номер не найден.", show_alert=True)

    number_text = binding.get("number") or binding.get("text")
    code_type = "первый" if call.data == "request_code1" else "второй"

    sent = await bot.send_message(
        chat_id=binding["group_id"],
        message_thread_id=binding["topic_id"],
        reply_to_message_id=binding["orig_msg_id"],
        text=f"Запрос {code_type} код для номера {number_text}. Ответьте кодом.",
    )

    pending_code_requests[sent.message_id] = {
        "type": code_type,
        "target_chat_id": call.message.chat.id,
        "target_message_id": msg_id,
    }

    await call.answer("Запрос отправлен")


@router.message(lambda m: m.reply_to_message and m.reply_to_message.message_id in pending_code_requests)
async def handle_code_response(msg: Message) -> None:
    req = pending_code_requests.pop(msg.reply_to_message.message_id, None)
    if not req:
        return
    code = msg.text.strip()
    label = "Первый" if req["type"] == "первый" else "Второй"
    await bot.send_message(
        req["target_chat_id"],
        f"{label} код: {code}",
        reply_to_message_id=req["target_message_id"],
    )


@router.callback_query(F.data == "mts_calls")
async def handle_mts_calls(call: CallbackQuery) -> None:
    binding = bindings.get(str(call.message.message_id))
    if not binding:
        return await call.answer("⚠️ Номер не найден.", show_alert=True)
    await bot.send_message(
        chat_id=binding["group_id"],
        message_thread_id=binding["topic_id"],
        reply_to_message_id=binding["orig_msg_id"],
        text="Пожалуйста, подключите МТС звонки, тутор есть в группе",
    )
    await call.answer("Отправлено")


@router.callback_query(F.data == "neg_balance")
async def handle_negative_balance(call: CallbackQuery) -> None:
    binding = bindings.get(str(call.message.message_id))
    if not binding:
        return await call.answer("⚠️ Номер не найден.", show_alert=True)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("Да", callback_data=f"balance_yes:{call.message.message_id}"),
         InlineKeyboardButton("Нет", callback_data=f"balance_no:{call.message.message_id}")]
    ])

    sent = await bot.send_message(
        chat_id=binding["group_id"],
        message_thread_id=binding["topic_id"],
        reply_to_message_id=binding["orig_msg_id"],
        text="Ваш баланс минусовой, будете пополнять?",
        reply_markup=keyboard,
    )

    pending_balance_requests[sent.message_id] = {
        "target_chat_id": call.message.chat.id,
        "target_message_id": call.message.message_id,
        "drop_id": binding.get("drop_id"),
    }

    await call.answer("Запрос отправлен")


@router.callback_query(F.data.startswith("balance_"))
async def handle_balance_choice(call: CallbackQuery) -> None:
    action, _ = call.data.split(":", 1)
    info = pending_balance_requests.get(call.message.message_id)
    if not info:
        return await call.answer("Не найдено", show_alert=True)

    drop_id = info.get("drop_id")
    if drop_id and call.from_user.id != drop_id:
        return await call.answer("Не для вас", show_alert=True)

    text = "Пополнит баланс" if action == "balance_yes" else "Не будет пополнять"
    await bot.send_message(
        info["target_chat_id"],
        text,
        reply_to_message_id=info["target_message_id"],
    )
    await call.message.edit_text(f"Ответ: {'Да' if action == 'balance_yes' else 'Нет'}")
    pending_balance_requests.pop(call.message.message_id, None)
    await call.answer("Ответ отправлен")
