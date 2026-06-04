"""Tests for QQ bot authorization logic.

Covers the _is_authorized_interaction_for_session method,
particularly the fix for #39110 where ``dm`` chat_type was missing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from gateway.platforms.qqbot.adapter import QQAdapter
from gateway.platforms.qqbot.keyboards import InteractionEvent


def _make_adapter():
    """Create a bare QQAdapter instance for testing static/helper methods."""
    return object.__new__(QQAdapter)


def _make_event(operator_openid: str = "user_abc") -> InteractionEvent:
    """Build an InteractionEvent with the given operator."""
    return InteractionEvent(
        id="evt_001",
        type=11,
        chat_type=2,
        scene="c2c",
        group_openid="",
        group_member_openid="",
        user_openid=operator_openid,
    )


# ---------------------------------------------------------------------------
# _parse_gateway_session_key
# ---------------------------------------------------------------------------


class TestParseGatewaySessionKey:
    """Tests for the static parser that _is_authorized relies on."""

    def test_dm_private_chat(self):
        """session_key with ``dm`` chat_type parses correctly."""
        result = QQAdapter._parse_gateway_session_key(
            "agent:main:qqbot:dm:8B2B..."
        )
        assert result == {
            "platform": "qqbot",
            "chat_type": "dm",
            "chat_id": "8B2B...",
        }

    def test_c2c_private_chat(self):
        """session_key with ``c2c`` chat_type parses correctly."""
        result = QQAdapter._parse_gateway_session_key(
            "agent:main:qqbot:c2c:user_xyz"
        )
        assert result == {
            "platform": "qqbot",
            "chat_type": "c2c",
            "chat_id": "user_xyz",
        }

    def test_with_user_id_suffix(self):
        """session_key with user_id suffix still parses correctly."""
        result = QQAdapter._parse_gateway_session_key(
            "agent:main:qqbot:dm:chat_123:user_456"
        )
        assert result["chat_type"] == "dm"
        assert result["chat_id"] == "chat_123"
        assert result.get("user_id") == "user_456"

    def test_invalid_key_returns_none(self):
        """Malformed session_key returns None."""
        assert QQAdapter._parse_gateway_session_key("") is None
        assert QQAdapter._parse_gateway_session_key("invalid") is None
        assert QQAdapter._parse_gateway_session_key("x:y:z") is None


# ---------------------------------------------------------------------------
# _is_authorized_interaction_for_session
# ---------------------------------------------------------------------------


class TestIsAuthorizedInteraction:
    """Tests for the authorization check (the fix in #39110)."""

    @pytest.mark.parametrize(
        "chat_type, session_key",
        [
            pytest.param("c2c", "agent:main:qqbot:c2c:user_abc", id="c2c_private"),
            pytest.param("dm", "agent:main:qqbot:dm:user_abc", id="dm_private"),
        ],
    )
    def test_matching_operator_is_authorized(self, chat_type, session_key):
        """Matching operator + chat_id is authorized for both c2c and dm."""
        adapter = _make_adapter()
        event = _make_event(operator_openid="user_abc")

        with patch.object(
            QQAdapter,
            "_parse_gateway_session_key",
            return_value={
                "platform": "qqbot",
                "chat_type": chat_type,
                "chat_id": "user_abc",
            },
        ):
            result = adapter._is_authorized_interaction_for_session(event, session_key)

        assert result is True

    @pytest.mark.parametrize(
        "chat_type, session_key",
        [
            pytest.param("c2c", "agent:main:qqbot:c2c:user_abc", id="c2c_private"),
            pytest.param("dm", "agent:main:qqbot:dm:user_abc", id="dm_private"),
        ],
    )
    def test_mismatched_operator_is_rejected(self, chat_type, session_key):
        """Non-matching operator is rejected for both c2c and dm."""
        adapter = _make_adapter()
        event = _make_event(operator_openid="attacker")

        with patch.object(
            QQAdapter,
            "_parse_gateway_session_key",
            return_value={
                "platform": "qqbot",
                "chat_type": chat_type,
                "chat_id": "user_abc",
            },
        ):
            result = adapter._is_authorized_interaction_for_session(event, session_key)

        assert result is False

    def test_invalid_platform_rejected(self):
        """Non-qqbot platform is rejected."""
        adapter = _make_adapter()
        event = _make_event()

        with patch.object(
            QQAdapter,
            "_parse_gateway_session_key",
            return_value={"platform": "telegram", "chat_type": "dm", "chat_id": "x"},
        ):
            result = adapter._is_authorized_interaction_for_session(
                event, "agent:main:telegram:dm:x"
            )

        assert result is False

    def test_empty_operator_rejected(self):
        """Empty operator_openid is rejected."""
        adapter = _make_adapter()
        event = _make_event(operator_openid="")

        with patch.object(
            QQAdapter,
            "_parse_gateway_session_key",
            return_value={
                "platform": "qqbot",
                "chat_type": "dm",
                "chat_id": "user_abc",
            },
        ):
            result = adapter._is_authorized_interaction_for_session(
                event, "agent:main:qqbot:dm:user_abc"
            )

        assert result is False
