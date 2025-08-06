import json
import os
import asyncio
from datetime import datetime

from .queue import number_queue, user_queue, bindings, IGNORED_TOPICS, active_numbers
from .config import logger
from .utils import phone_pattern

QUEUE_FILE = 'number_queue.json'
USER_FILE = 'user_queue.json'
BINDINGS_FILE = 'bindings.json'
HISTORY_FILE = 'history.json'
IGNORED_FILE = 'ignored_topics.json'
ISSUED_FILE = 'issued_numbers.json'

history = []
issued_numbers = []

_save_task = None
_pending_save = False
_SAVE_DELAY = 0.5


def save_data():
    """Schedule data persistence without blocking the event loop."""
    global _save_task, _pending_save
    _pending_save = True
    loop = asyncio.get_event_loop()
    if not _save_task or _save_task.done():
        _save_task = loop.create_task(_delayed_save())


async def _delayed_save():
    global _pending_save
    await asyncio.sleep(_SAVE_DELAY)
    if not _pending_save:
        return
    _pending_save = False
    await asyncio.to_thread(_write_data)


def _write_data():
    with open(QUEUE_FILE, 'w') as f:
        json.dump(list(number_queue), f)
    with open(USER_FILE, 'w') as f:
        json.dump(list(user_queue), f)
    with open(BINDINGS_FILE, 'w') as f:
        json.dump(bindings, f)
    with open(IGNORED_FILE, 'w') as f:
        json.dump(list(IGNORED_TOPICS), f)
    with open(ISSUED_FILE, 'w') as f:
        json.dump(issued_numbers, f)
    logger.info(
        "[SAVE] numbers=%d users=%d bindings=%d ignored=%d issued=%d",
        len(number_queue),
        len(user_queue),
        len(bindings),
        len(IGNORED_TOPICS),
        len(issued_numbers),
    )


def load_data():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r') as f:
            for item in json.load(f):
                if isinstance(item.get('timestamp'), str):
                    item['timestamp'] = datetime.fromisoformat(item['timestamp']).timestamp()
                number_queue.append(item)
                num = item.get('number')
                if not num:
                    match = phone_pattern.search(item.get('text', ''))
                    if match:
                        num = match.group(0)
                        item['number'] = num
                if num:
                    active_numbers.add(num)
    if os.path.exists(USER_FILE):
        with open(USER_FILE, 'r') as f:
            for item in json.load(f):
                if isinstance(item.get('timestamp'), str):
                    item['timestamp'] = datetime.fromisoformat(item['timestamp']).timestamp()
                user_queue.append(item)
    if os.path.exists(BINDINGS_FILE):
        with open(BINDINGS_FILE, 'r') as f:
            loaded = json.load(f)
            for key, value in loaded.items():
                num = value.get('number')
                if not num:
                    match = phone_pattern.search(value.get('text', ''))
                    if match:
                        num = match.group(0)
                        value['number'] = num
                if num:
                    active_numbers.add(num)
            bindings.update(loaded)
    if os.path.exists(IGNORED_FILE):
        with open(IGNORED_FILE, 'r') as f:
            IGNORED_TOPICS.update(json.load(f))
    if os.path.exists(ISSUED_FILE):
        with open(ISSUED_FILE, 'r') as f:
            issued_numbers.extend(json.load(f))
    logger.info(
        "[LOAD] numbers=%d users=%d bindings=%d ignored=%d issued=%d",
        len(number_queue),
        len(user_queue),
        len(bindings),
        len(IGNORED_TOPICS),
        len(issued_numbers),
    )


def load_history():
    global history
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
    logger.info("[LOAD HISTORY] entries=%d", len(history))


def save_history():
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f)
    logger.info("[SAVE HISTORY] entries=%d", len(history))
