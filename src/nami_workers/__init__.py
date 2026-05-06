"""Nami Workers — pluggable task handlers, each harnessed.

Every worker is a callable that takes a payload dict and returns
an output dict. Workers are registered with Hermes and wrapped
by HarnessRuntime for safety, quality, and audit.
"""

from .registry import WorkerRegistry, register_worker, get_worker
from .utils import ai_chat_completion, telegram_send, oanda_paper_trade
from .signal_worker import signal_worker
from .proxy_worker import proxy_worker
from .lottery_worker import lottery_worker
from .bot_worker import bot_worker
from .trading_worker import trading_worker
from .gateway_worker import gateway_worker
from .status_worker import status_worker
from .bridge_worker import bridge_worker
from .graphify_worker import graphify_worker
from .miroshark_worker import miroshark_worker
from .gold_worker import gold_worker
from .notification_worker import notification_worker
from .analytics_worker import analytics_worker
from .scheduler_worker import scheduler_worker
from .cron_worker import cron_worker
from .email_worker import email_worker
from .relay_worker import relay_worker
from .pipeline_worker import pipeline_worker
from .ai_chat_worker import ai_chat_worker
from .sentiment_worker import sentiment_worker
from .search_worker import search_worker

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
    "miroshark": miroshark_worker,
    "gold": gold_worker,
    "notification": notification_worker,
    "analytics": analytics_worker,
    "scheduler": scheduler_worker,
    "cron": cron_worker,
    "email": email_worker,
    "relay": relay_worker,
    "pipeline": pipeline_worker,
    "ai_chat": ai_chat_worker,
    "sentiment": sentiment_worker,
    "search": search_worker,
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
    "miroshark_worker",
    "gold_worker",
    "notification_worker",
    "analytics_worker",
    "scheduler_worker",
    "cron_worker",
    "email_worker",
    "relay_worker",
    "pipeline_worker",
    "ai_chat_worker",
    "sentiment_worker",
    "search_worker",
]
