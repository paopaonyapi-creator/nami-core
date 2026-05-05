"""Nami Workers — pluggable task handlers, each harnessed.

Every worker is a callable that takes a payload dict and returns
an output dict. Workers are registered with Hermes and wrapped
by HarnessRuntime for safety, quality, and audit.
"""

from .registry import WorkerRegistry, register_worker, get_worker

__all__ = [
    "WorkerRegistry",
    "register_worker",
    "get_worker",
]
