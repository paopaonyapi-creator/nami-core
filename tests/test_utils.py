"""Tests for nami_workers.utils — shared utilities."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from nami_workers.utils import telegram_send, ai_chat_completion, oanda_paper_trade


def test_telegram_send_no_token() -> None:
    """telegram_send returns error when no token configured."""
    result = telegram_send("123", "hello")
    assert result["ok"] is False
    assert result.get("error") in ("no_token", "no_api_key")


def test_telegram_send_with_mock() -> None:
    """telegram_send works when API responds ok."""
    with patch("nami_workers.utils._get_telegram_token", return_value="fake-token"):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "result": {}}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("nami_workers.utils.urllib.request.urlopen", return_value=mock_resp):
            result = telegram_send("123", "hello")
            assert result["ok"] is True


def test_ai_chat_completion_no_config() -> None:
    """ai_chat_completion returns error when no proxy or API key available."""
    import urllib.error

    # Both proxy and direct API fail with URLError (caught by the function)
    with patch("nami_workers.utils.urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        with patch("nami_workers.utils._get_ai_config", return_value={}):
            result = ai_chat_completion([{"role": "user", "content": "test"}])
            assert "content" in result
            assert result["provider"] == "none"


def test_oanda_paper_trade_no_config() -> None:
    """oanda_paper_trade returns error when not configured."""
    result = oanda_paper_trade("XAU_USD", 1, "Long")
    assert "error" in result or "mode" in result
