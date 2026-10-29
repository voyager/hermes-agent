"""Tests for the local (voyager) Telegram patches: cu: container-update
buttons and clarify buttons captioned with their option text."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)

import plugins.platforms.telegram.adapter as tg
from plugins.platforms.telegram.adapter import TelegramAdapter, _clarify_button_label
from gateway.config import PlatformConfig


def _make_adapter():
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="test-token", extra={}))
    adapter._bot = AsyncMock()
    adapter._app = MagicMock()
    return adapter


def _query(data):
    q = MagicMock()
    q.data = data
    q.answer = AsyncMock()
    q.message = MagicMock()
    q.message.edit_reply_markup = AsyncMock()
    q.from_user.id = 196698088
    q.from_user.first_name = "Mario"
    return q


async def _tap(adapter, data):
    q = _query(data)
    update = MagicMock()
    update.callback_query = q
    await adapter._handle_callback_query(update, MagicMock())
    return q


class TestClarifyButtonLabel:
    def test_short_label_kept(self):
        assert _clarify_button_label("Update all", 0) == "Update all"

    def test_long_label_truncated_to_30(self):
        label = _clarify_button_label("x" * 50, 3)
        assert len(label) == 30 and label.endswith("…")

    def test_blank_label_falls_back_to_number(self):
        assert _clarify_button_label("   ", 2) == "3"


class TestContainerUpdateButton:
    @pytest.mark.asyncio
    async def test_malformed_plan_id_does_nothing(self):
        adapter = _make_adapter()
        with patch.object(tg, "_launch_container_update_worker") as launch, \
             patch.object(tg, "_container_update_plan_verdict") as verdict:
            q = await _tap(adapter, "cu:../../etc; rm -rf")
        verdict.assert_not_called()
        launch.assert_not_called()
        q.answer.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_unauthorized_user_cannot_launch(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_is_callback_user_authorized", return_value=False), \
             patch.object(tg, "_launch_container_update_worker") as launch, \
             patch.object(tg, "_container_update_plan_verdict") as verdict:
            q = await _tap(adapter, "cu:20261029-210000")
        verdict.assert_not_called()
        launch.assert_not_called()
        assert "not authorized" in q.answer.await_args.kwargs["text"]

    @pytest.mark.asyncio
    async def test_stale_plan_alerts_and_does_not_launch(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_is_callback_user_authorized", return_value=True), \
             patch.object(tg, "_launch_container_update_worker") as launch, \
             patch.object(tg, "_container_update_plan_verdict",
                          return_value={"ok": False, "reason": "Plan expired."}):
            q = await _tap(adapter, "cu:20261029-210000")
        launch.assert_not_called()
        q.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        assert q.answer.await_args.kwargs == {"text": "Plan expired.", "show_alert": True}

    @pytest.mark.asyncio
    async def test_valid_plan_launches_worker(self):
        adapter = _make_adapter()
        with patch.object(adapter, "_is_callback_user_authorized", return_value=True), \
             patch.object(tg, "_launch_container_update_worker", return_value=True) as launch, \
             patch.object(tg, "_container_update_plan_verdict",
                          return_value={"ok": True, "pending": 3}):
            q = await _tap(adapter, "cu:20261029-210000")
        launch.assert_called_once_with("20261029-210000")
        q.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
        assert q.answer.await_args.kwargs["text"] == "Applying 3 updates…"
