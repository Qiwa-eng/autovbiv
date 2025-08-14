from collections import deque
import asyncio

number_queue = deque()
user_queue = deque()
bindings = {}
contact_bindings = {}
blocked_numbers = {}
IGNORED_TOPICS = set()
contact_requests = {}
active_numbers = set()
pending_code_requests = {}
pending_balance_requests = {}

# Locks for async-safe operations on queues
number_queue_lock = asyncio.Lock()
user_queue_lock = asyncio.Lock()

# Global work state
WORKING = True
start_task = None
