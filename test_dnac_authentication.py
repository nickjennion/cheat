"""Token mint/refresh behavior for DNACClient."""

from unittest.mock import MagicMock

import requests

from dnac_client import DNACClient


def _client_with_auth_session(monkeypatch):
    client = DNACClient("dnac.example", "user", "password")
    auth_session = MagicMock()
    monkeypatch.setattr(client, "_new_session", MagicMock(return_value=auth_session))
    monkeypatch.setattr(client, "_save_token", MagicMock())
    return client, auth_session


def test_reauth_uses_fresh_session_and_atomically_replaces_token(monkeypatch):
    client, auth_session = _client_with_auth_session(monkeypatch)
    client.token = "expired-token"
    client.session.headers["X-Auth-Token"] = "expired-token"
    client.session.cookies.set("stale", "cookie")
    client.session.post = MagicMock(side_effect=AssertionError("data session was reused"))

    response = MagicMock()
    response.json.return_value = {"Token": "new-token"}
    response.raise_for_status.return_value = None
    auth_session.post.return_value = response

    assert client.authenticate() is True
    assert client.token == "new-token"
    client._save_token.assert_called_once_with("new-token")
    _, kwargs = auth_session.post.call_args
    assert kwargs["auth"] == ("user", "password")
    assert kwargs["headers"] == {"Content-Type": "application/json"}
    assert "X-Auth-Token" not in kwargs["headers"]
    auth_session.close.assert_called_once()


def test_401_preserves_existing_token_and_prints_sanitized_reason(monkeypatch, capsys):
    client, auth_session = _client_with_auth_session(monkeypatch)
    client.token = "expired-token"
    response = MagicMock(status_code=401, reason="Unauthorized")
    response.json.return_value = {"response": {"message": "Invalid credentials"}}
    response.raise_for_status.side_effect = requests.HTTPError(response=response)
    auth_session.post.return_value = response

    assert client.authenticate() is False
    assert client.token == "expired-token"
    assert "(HTTP 401 Unauthorized): Invalid credentials" in capsys.readouterr().out
    client._save_token.assert_not_called()


def test_success_response_without_token_preserves_existing_token(monkeypatch, capsys):
    client, auth_session = _client_with_auth_session(monkeypatch)
    client.token = "expired-token"
    response = MagicMock()
    response.json.return_value = {"status": "ok"}
    response.raise_for_status.return_value = None
    auth_session.post.return_value = response

    assert client.authenticate() is False
    assert client.token == "expired-token"
    assert "returned no valid Token" in capsys.readouterr().out
    client._save_token.assert_not_called()


def test_invalid_json_preserves_existing_token(monkeypatch, capsys):
    client, auth_session = _client_with_auth_session(monkeypatch)
    client.token = "expired-token"
    response = MagicMock()
    response.json.side_effect = ValueError("not JSON")
    response.raise_for_status.return_value = None
    auth_session.post.return_value = response

    assert client.authenticate() is False
    assert client.token == "expired-token"
    assert "invalid token response" in capsys.readouterr().out
