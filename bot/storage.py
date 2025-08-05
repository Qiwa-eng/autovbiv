import json
import os
from collections import deque

from .queue import number_queue, user_queue, bindings, IGNORED_TOPICS
from .config import logger

QUEUE_FILE = 'number_queue.json'
USER_FILE = 'user_queue.json'
BINDINGS_FILE = 'bindings.json'
HISTORY_FILE = 'history.json'
IGNORED_FILE = 'ignored_topics.json'

history = []


def save_data():
    with open(QUEUE_FILE, 'w') as f:
        json.dump(list(number_queue), f)
    with open(USER_FILE, 'w') as f:
        json.dump(list(user_queue), f)
    with open(BINDINGS_FILE, 'w') as f:
        json.dump(bindings, f)
    with open(IGNORED_FILE, 'w') as f:
        json.dump(list(IGNORED_TOPICS), f)
    logger.info(
        "[SAVE] numbers=%d users=%d bindings=%d ignored=%d",
        len(number_queue),
        len(user_queue),
        len(bindings),
        len(IGNORED_TOPICS),
    )


def load_data():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE, 'r') as f:
            number_queue.extend(deque(json.load(f)))
    if os.path.exists(USER_FILE):
        with open(USER_FILE, 'r') as f:
            user_queue.extend(deque(json.load(f)))
    if os.path.exists(BINDINGS_FILE):
        with open(BINDINGS_FILE, 'r') as f:
            bindings.update(json.load(f))
    if os.path.exists(IGNORED_FILE):
        with open(IGNORED_FILE, 'r') as f:
            IGNORED_TOPICS.update(json.load(f))
    logger.info(
        "[LOAD] numbers=%d users=%d bindings=%d ignored=%d",
        len(number_queue),
        len(user_queue),
        len(bindings),
        len(IGNORED_TOPICS),
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
