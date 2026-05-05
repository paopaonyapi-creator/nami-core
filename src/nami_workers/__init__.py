"""Nami Workers — pluggable task handlers, each harnessed.

Every worker is a callable that takes a payload dict and returns
an output dict. Workers are registered with Hermes and wrapped
by HarnessRuntime for safety, quality, and audit.
"""

from .registry import WorkerRegistry, register_worker, get_worker
from .signal_worker import signal_worker
from .proxy_worker import proxy_worker
from .lottery_worker import lottery_worker
from .bot_worker import bot_worker
from .trading_worker import trading_worker
from .gateway_worker import gateway_worker
from .status_worker import status_worker
from .bridge_worker import bridge_worker
from .graphify_worker import graphify_worker

ALL_WORKERS = {
    "signal": signal_worker,
    "proxy": proxy_worker,
    "lottery": lottery_worker,
    "bot": bot_worker,
    "trading": trading_worker,
    "gateway": gateway_worker,
    "status": status_worker,
    "bridge": bridge_worker,
    "graphify": graphify_worker,
}

__all__ = [
    "WorkerRegistry",
    "register_worker",
    "get_worker",
    "ALL_WORKERS",
    "signal_worker",
    "proxy_worker",
    "lottery_worker",
    "bot_worker",
    "trading_worker",
    "gateway_worker",
    "status_worker",
    "bridge_worker",
    "graphify_worker",
]
