import logging
import json
import re
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from collections import deque
from datetime import datetime
from statistics import mean
import asyncio

API_TOKEN = '7625642691:AAFa41xZsEv2eFxqyoTZ6dTX4nfY6itgScw'
GROUP1_ID = -1002816304860
GROUP2_IDS = [-1002569933724, -1002514580090, -1002799832189, -1002554415803, -1002537566318]

TOPIC_IDS_GROUP1 = [72295, 72290]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)

phone_pattern = re.compile(
    r"(?:\+7|7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}|\b\d{10}\b"
)
from datetime import datetime, timedelta

blocked_numbers = {} 
from datetime import datetime, timedelta
history_file = "history.json"
history = [] 
last_empty_alert = None
history[:] = history[-50:]

number_queue = deque()
user_queue = deque()
bindings = {}

QUEUE_FILE = "number_queue.json"
USER_FILE = "user_queue.json"
BINDINGS_FILE = "bindings.json"
queued_numbers_set = set()


def save_data():
    with open(QUEUE_FILE, 'w') as f:
        json.dump(list(number_queue), f)
    with open(USER_FILE, 'w') as f:
        json.dump(list(user_queue), f)
    with open(BINDINGS_FILE, 'w') as f:
        json.dump(bindings, f)
def load_history():
    global history
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            history = json.load(f)

def save_history():
    with open(history_file, "w") as f:
        json.dump(history, f)


def load_data():
    global number_queue, user_queue, bindings
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r') as f:
            number_queue = deque(json.load(f))
    if os.path.exists(USER_FILE):
        with open(USER_FILE, 'r') as f:
            user_queue = deque(json.load(f))
    if os.path.exists(BINDINGS_FILE):
        with open(BINDINGS_FILE, 'r') as f:
            bindings = json.load(f)

@dp.message_handler(lambda msg: msg.text.lower() == "номер")
async def handle_number_request(msg: types.Message):
    if msg.chat.type == "private":
        return await msg.reply("❌ Команда <b>номер</b> работает только в группе.", parse_mode="HTML")

    if msg.message_thread_id in IGNORED_TOPICS:
        return await msg.reply("⚠️ В этой теме бот не работает. Активируйте её командой /work.")

    if msg.chat.id not in GROUP2_IDS:
        return

    for entry in user_queue:
        if entry['user_id'] == msg.from_user.id:
            return await msg.reply("⚠️ Вы уже в очереди на номер.")

    if number_queue:
        number = number_queue.popleft()

        message_text = (
           f"<b>Ваш номер:</b> {number['text']}\n"
           f"<code>Нажмите \"Ответить\" и отправьте код от номера</code>\n\n"
           f"❗️ <b>Если выбивает ошибку</b> — сразу кидайте <u>скриншот ошибки</u> так же ответом.\n"
           f"Без скрина вас будут дрочить этим номером и закидывать повторками."
        )

        sent = await bot.send_message(
            chat_id=msg.chat.id,
            text=message_text,
            reply_to_message_id=msg.message_id,
            reply_markup=get_number_action_keyboard()
        )

        bindings[str(sent.message_id)] = {
            "orig_msg_id": number['message_id'],
            "topic_id": number['topic_id'],
            "group_id": number['from_group_id'],
            "user_id": msg.from_user.id,
            "text": number['text'],
            "added_at": number.get("added_at")
        }

        save_data()
        logger.info(f"[ВЫДАН НОМЕР] {number['text']} → user_id={msg.from_user.id}")

    else:
        position = len(user_queue) + 1

        notify = await msg.reply(
            f"⏳ Номеров нет, вы в очереди ({position})",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("Выйти из очереди", callback_data="leave_queue")
            )
        )

        user_queue.append({
            "user_id": msg.from_user.id,
            "chat_id": msg.chat.id,
            "request_msg_id": msg.message_id,
            "timestamp": datetime.utcnow().isoformat(),
            "notify_msg_id": notify.message_id
        })

        save_data()
        await try_dispatch_next()
        await update_queue_messages()


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_number_action_keyboard():
    return InlineKeyboardMarkup().add(
        InlineKeyboardButton("🔁 Скип", callback_data="skip_number"),
        InlineKeyboardButton("❌ Ошибка", callback_data="error_reason")
    )

@dp.callback_query_handler(lambda c: c.data == "error_reason")
async def error_reason_menu(call: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup().add(
        InlineKeyboardButton("❌ Моментальная ошибка", callback_data="error_ban"),
        InlineKeyboardButton("⌛ Не ввели код", callback_data="error_noban")
    )
    await call.message.edit_reply_markup(reply_markup=keyboard)

async def update_queue_messages():
    for idx, user in enumerate(sorted(user_queue, key=lambda x: x["timestamp"])):
        try:
            position = idx + 1
            await bot.edit_message_text(
                chat_id=user["chat_id"],
                message_id=user["notify_msg_id"],
                text=f"⏳ Номеров нет, вы в очереди ({position})",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("Выйти из очереди", callback_data="leave_queue")
                )
            )
        except Exception as e:
            logger.warning(f"[ОШИБКА ОБНОВЛЕНИЯ ОЧЕРЕДИ] user_id={user['user_id']}: {e}")
@dp.message_handler(commands=["work"])
async def remove_topic_from_ignore(msg: types.Message):
    if msg.is_topic_message:
        if msg.message_thread_id in IGNORED_TOPICS:
            IGNORED_TOPICS.remove(msg.message_thread_id)
            await msg.reply("✅ Эта тема снова активна. Бот теперь реагирует на номера.")
        else:
            await msg.reply("ℹ️ Эта тема и так уже активна.")
    else:
        await msg.reply("⚠️ Команду можно использовать только в теме.")

@dp.message_handler(commands=["очистить"])
async def handle_clear_queue(msg: types.Message):
    if msg.chat.id not in GROUP2_IDS:
        return

    # Очищаем очереди
    number_queue.clear()
    user_queue.clear()
    bindings.clear()
    save_data()

    # Сообщаем в каждой теме группы 1
    for topic_id in TOPIC_IDS_GROUP1:
        try:
            await bot.send_message(
                chat_id=GROUP1_ID,
                message_thread_id=topic_id,
                text="⚠️ Очередь очищена, продублируйте номера"
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

    from datetime import datetime

    num_numbers = len(number_queue)
    num_users = len(user_queue)

    # Примерное время ожидания
    if num_users == 0:
        est_wait = "Мгновенно"
    elif num_numbers == 0:
        est_wait = "ожидание номера"
    else:
        seconds_total = num_users * 30  # 30 сек на одного — условно
        minutes = seconds_total // 60
        seconds = seconds_total % 60
        est_wait = f"~{minutes} мин {seconds} сек"

    # Время последнего добавления номера
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

    number_queue.append({
        "message_id": binding["orig_msg_id"],
        "topic_id": binding["topic_id"],
        "text": number_text,
        "from_group_id": binding["group_id"],
        "added_at": binding.get("added_at", datetime.utcnow().timestamp())
    })

    try:
        await call.message.edit_text("🔁 Номер возвращён в очередь.")
    except:
        await call.message.reply("🔁 Номер возвращён в очередь.")

    logger.info(f"[СКИП] {number_text} → user_id={user_id}")

    # Удалить привязку
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
            "❌ Номер удалён.\n⛔ Заблокирован на 30 минут (моментальная ошибка)."
        )
        logger.info(f"[ОШИБКА С БАНОМ] {number_text} → user_id={user_id}")

    elif call.data == "error_noban":
        await call.message.edit_text(
            "❌ Номер удалён.\n⌛ Без блокировки (не пришёл код)."
        )
        logger.info(f"[ОШИБКА БЕЗ БАНА] {number_text} → user_id={user_id}")

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

IGNORED_TOPICS = set()

@dp.message_handler(commands=["nework"])
async def add_topic_to_ignore(msg: types.Message):
    if msg.is_topic_message:
        IGNORED_TOPICS.add(msg.message_thread_id)
        await msg.reply("✅ Эта тема теперь исключена. Бот не будет здесь реагировать на номера.")
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

        # Проверка на дубликат
        for item in number_queue:
            if number_text in item.get("text", ""):
                try:
                    orig_msg = await bot.get_message(GROUP1_ID, item['message_id'])
                    sender = orig_msg.from_user
                    if sender.username:
                        sender_mention = f"@{sender.username}"
                    else:
                        sender_mention = f'<a href="tg://user?id={sender.id}">{sender.full_name}</a>'
                except Exception:
                    sender_mention = "неизвестно"

                await bot.send_message(
                    chat_id=msg.chat.id,
                    message_thread_id=msg.message_thread_id,
                    reply_to_message_id=msg.message_id,
                    text=f"⚠️ Такой номер уже в очереди\n👤 Отправил: {sender_mention}",
                    parse_mode="HTML"
                )
                logger.info(f"[ДУБЛИКАТ В ОЧЕРЕДИ] {number_text}")
                return

        # Добавление номера в очередь
        number_queue.append({
            "message_id": msg.message_id,
            "topic_id": msg.message_thread_id,
            "text": msg.text,
            "from_group_id": msg.chat.id,
            "added_at": datetime.utcnow().timestamp()
        })
        save_data()

        # Расчёт примерного времени
        if history:
            avg_delay = int(mean(entry["delay"] for entry in history if "delay" in entry))
            avg_delay = max(5, min(avg_delay, 1800))  # 5 сек – 30 мин
            minutes = avg_delay // 60
            seconds = avg_delay % 60
            estimate = f"{minutes} мин {seconds} сек"
        else:
            estimate = "недоступно"

        await bot.send_message(
            chat_id=msg.chat.id,
            message_thread_id=msg.message_thread_id,
            reply_to_message_id=msg.message_id,
            text=f"✅ Взял номер\n\n⏱ Примерное ожидание кода: <b>{estimate}</b>",
            parse_mode="HTML"
        )

        logger.info(f"[НОМЕР ПРИНЯТ] {number_text} из темы {msg.message_thread_id}")
        await try_dispatch_next()



@dp.callback_query_handler(lambda c: c.data == "leave_queue")
async def leave_queue(call: types.CallbackQuery):
    if call.message.chat.id not in GROUP2_IDS:
        return

    # Ищем участника в очереди
    removed = False
    new_queue = deque()
    for u in user_queue:
        if u['user_id'] == call.from_user.id:
            removed = True
        else:
            new_queue.append(u)

    if removed:
        user_queue.clear()
        user_queue.extend(new_queue)

        try:
            await call.message.edit_text("❌ Вы вышли из очереди.")
        except Exception:
            await call.message.reply("❌ Вы вышли из очереди.")
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
            reply_to_message_id=binding['orig_msg_id']
        )

        await msg.reply("✅ Код был успешно отправлен")

        # Статистика
        added_at = binding.get("added_at")
        if added_at:
            now = datetime.utcnow().timestamp()
            delay = now - added_at
            history.append({
                "added": added_at,
                "responded": now,
                "delay": delay
            })
            history[:] = history[-50:]
            save_history()
            logger.info(f"[КОД ПОЛУЧЕН] user_id={binding['user_id']} — ожидание {int(delay)} сек")

    except Exception as e:
        logger.warning(f"[ОШИБКА ОТПРАВКИ КОДА] {e}")
        await msg.reply(
            "❌ Не удалось отправить код.\n"
            "Пожалуйста, запросите новый номер — он не найден в чате с номерами."
        )

    finally:
        del bindings[str(msg.reply_to_message.message_id)]
        save_data()


async def joke_dispatcher():
    sent_users = set()

    while True:
        now = datetime.utcnow().timestamp()

        for user in list(user_queue):
            ts = datetime.fromisoformat(user["timestamp"]).timestamp()

            # Ждёт дольше 60 сек и анекдот ещё не отправляли
            if now - ts >= 60 and user['user_id'] not in sent_users:
                joke = await fetch_russian_joke()

                try:
                    await bot.send_message(
                        chat_id=user["chat_id"],
                        text=f"🕓 Пока вы ждёте, вот вам анекдот:\n\n<code>{joke}</code>",
                        parse_mode="HTML",
                        reply_to_message_id=user.get("request_msg_id")  # Отправляем в тему, ответом
                    )
                    sent_users.add(user['user_id'])

                except Exception as e:
                    logger.warning(f"[АНЕКДОТ] user_id={user['user_id']}: {e}")

        await asyncio.sleep(30)


JOKES = [
    # Оригинальные из Часть 1 (около 20)
    "— Мама, что такое черный юмор? — Сынок, видишь вон там мужчину без рук? Вели ему похлопать в ладоши. — Я же слепой! — Вот именно.",
    "Я копал яму в саду и вдруг откопал целый сундук с золотом. Потом вспомнил, зачем я копал яму.",
    "— Будешь выходить — труп вынеси! — Может мусор? — Может мусор, может сантехник, бог его знает…",
    "Проблема не сунуть лампочку в рот, проблема вызвать потом «скорую помощь».",
    "Одну девочку в школе звали Крокодилом. Не потому что уродина, а потому что однажды затащила в реку оленя и сожрала его.",
    "— Я боюсь прыгать — вдруг парашют не раскроется? — Ещё никто никогда не жаловался, что у него не раскрылся парашют.",
    "— Почему-то, когда вы улыбаетесь, один глаз весёлый, другой грустный‑грустный… — Весёлый — это искусственный.",
    "Из записи в книге жалоб и предложений: «Верёвки в хозяйственном, мыло в косметическом, табуретки на другом этаже».",
    "— Ура, я поступила в автошколу. Скоро будет на одного пешехода меньше! — А может просто не произойдёт...",
    "Когда изобретатель USB‑порта умер, его гроб сначала опустили, потом перевернули и опустили снова.",
    "— Моя девушка порвала со мной, я забрал её кресло‑каталку. Угадайте, кто приполз ко мне на коленях?",
    "Если бы моя бабушка знала, сколько денег я сэкономил на её похоронах, она бы перевернулась в канаве.",
    "31 декабря. Мужик ставит табуретку и верёвку на люстру. Вваливается пьяный Дед Мороз… оценивает ситуацию: «М‑да?.. Ну, раз ты всё равно на табуреточке...»",
    "Зажги человеку костёр — ему тепло до конца дня. Зажги одежду — тепло до конца жизни.",
    "Акробат умер на батуте, но ещё какое-то время продолжал радовать публику.",
    "Шутки про утопленников обычно несмешные, потому что лежат на поверхности.",
    "— Кот умер год назад. Я до сих пор замедляю шаг там, где он любил лежать. — Может, пора его похоронить?",
    "— Доктор, я съел пиццу вместе с упаковкой. Я умру? — Ну, все когда-нибудь умрут… — Все умрут! Ужас, что я наделал!",
    "Однорукий человек заплакал, увидев магазин «секонд‑хенд».",
    "> Когда ты умер, ты об этом не знаешь, только другим тяжело. То же самое, когда ты тупой."
    ,
    # Оригинальные из Часть 2 (~20)
    "— Доктор! В моей палате умирает уже девятый пациент. Почему бы вам не открыть отдельную палату для обречённых? — Это она и есть.",
    "— Извините, а какой здесь пароль от вай‑фая? — Это же похороны! — «Похороны» с маленькой или большой?",
    "Чем старее становлюсь, тем чаще вспоминаю всех, кого потерял навсегда. Работать туристическим гидом было плохой идеей.",
    "В Таджикистане землетрясение. Погибло 300 000 таджиков. Америка послала деньги, Германия — продукты, Россия — 300 000 таджиков.",
    "Чтобы проверить, курю я или нет, родители оставляли газ включённым.",
    "Фальшивого дрессировщика в цирке быстро раскусили.",
    "Прочитал, что на Кавказе каждые две минуты протыкают человека ножом. Жалко бедолагу.",
    "> Борода придаёт загадочности: никогда не знаешь, что поведёт человек, если поджечь ему бороду.",
    "Соседи пьют, дерутся и поют. Решил переехать, осталось дождаться, когда они вместе дорогу переходить будут.",
    "— Бабушка, зачем удалилась из «Одноклассников»? — Одноклассники кончились.",
    "Гражданская война. Белые ведут большевика на расстрел. Ночь, ветер, ливень. — Тебе что? — А нам ещё назад возвращаться.",
    "«Я что‑то нажал, и всё исчезло». Курт Кобейн.",
    "«Минус на минус даёт плюс. Поэтому ядовитые грибы запиваю метиловым спиртом.»",
    "«Иду себе… безрукий мальчик». Так начинается каждый рассказ безрукого.",
    "Слепой в магазине раскручивает поводыря над головой: «Осматриваюсь».",
    "Беда не придёт одна. После взрыва на цементном заводе пошёл дождь — жизнь окончательно замёрзла.",
    "Не нужно тыкать в меня пальцем. Ткните себе в глаз — чтоб меня не видеть.",
    "Окей, Google, можно ли хранить прах деда в банке из‑под Coca‑Cola, если имя подходит?",
    "— С кем пообедать? — Лучше с умершим. Ест мало, достанется больше.",
    "— Отдать почку больному человек любит. А пять — уже полиция.",
]

import aiohttp

import random

async def fetch_russian_joke():
    return random.choice(JOKES)



async def try_dispatch_next():
    # Если номеров нет, а кто-то ждёт — уведомляем в теме
    if not number_queue and user_queue:
        now = datetime.utcnow().timestamp()
        if not hasattr(try_dispatch_next, "last_notice") or now - try_dispatch_next.last_notice > 120:
            try_dispatch_next.last_notice = now
            for topic_id in TOPIC_IDS_GROUP1:
                try:
                    await bot.send_message(
                        chat_id=GROUP1_ID,
                        message_thread_id=topic_id,
                        text="🚨 Очередь номеров пуста! Самые быстрые коды на диком западе!"
                    )
                    logger.info(f"[ОПОВЕЩЕНИЕ] Пустая очередь → тема {topic_id}")
                except Exception as e:
                    logger.warning(f"[ОШИБКА ОПОВЕЩЕНИЯ] тема {topic_id}: {e}")
        return  # Номеров нет — заканчиваем

    # Пока есть и номера, и пользователи — обрабатываем
    while number_queue and user_queue:
        number = number_queue.popleft()
        sorted_users = sorted(user_queue, key=lambda u: datetime.fromisoformat(u['timestamp']))
        user = sorted_users[0]
        user_queue.remove(user)

        await update_queue_messages()

        message_text = (
           f"<b>Ваш номер:</b> {number['text']}\n"
           f"<code>Нажмите \"Ответить\" и отправьте код от номера</code>\n\n"
           f"❗️ <b>Если выбивает ошибку</b> — сразу кидайте <u>скриншот ошибки</u> так же ответом.\n"
           f"Без скрина вас будут дрочить этим номером и закидывать повторками."
        )
        try:
            sent = await bot.send_message(
                chat_id=user['chat_id'],
                text=message_text,
                reply_to_message_id=user['request_msg_id'],
                reply_markup=get_number_action_keyboard()
            )
        except Exception as e:
            logger.warning(f"[ОШИБКА ОТПРАВКИ] user_id={user['user_id']}: {e}")
            continue

        bindings[str(sent.message_id)] = {
            "orig_msg_id": number['message_id'],
            "topic_id": number['topic_id'],
            "group_id": number['from_group_id'],
            "user_id": user['user_id'],
            "text": number['text'],
            "added_at": number.get("added_at")
        }

        save_data()
        logger.info(f"[АВТОВЫДАЧА] {number['text']} → user_id={user['user_id']}")






if __name__ == '__main__':
    load_data()
    load_history()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(joke_dispatcher())
    logger.info("Бот запущен.")
    executor.start_polling(dp, skip_updates=True)
